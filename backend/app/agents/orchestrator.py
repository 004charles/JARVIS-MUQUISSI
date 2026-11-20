"""Phase 9 multi-step specialized agent orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ChatMessage
from app.ai.manager import ai_manager
from app.ai.prompts import build_jarvis_system_prompt
from app.ai.tool_orchestrator import extract_tool_call
from app.core.events import AssistantState, event_bus
from app.core.logging import get_logger
from app.database.models import AgentRunEntry, utcnow
from app.desktop import desktop_service
from app.system.telemetry import get_system_snapshot
from app.tools.registry import tool_registry

from .profiles import AGENT_PROFILES, AgentType, get_agent_profile, infer_agent_type

logger = get_logger("agents.orchestrator")


@dataclass(frozen=True)
class AgentRunResult:
    """Serialized mission result returned by AgentOrchestrator."""

    id: int
    agent_type: AgentType
    agent_name: str
    goal: str
    status: str
    steps: list[dict[str, Any]]
    summary: str
    created_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "goal": self.goal,
            "status": self.status,
            "steps": self.steps,
            "summary": self.summary,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class AgentOrchestrator:
    """Executes multi-step missions using scoped specialized agents and tools."""

    def list_profiles(self) -> list[dict[str, object]]:
        """Return metadata for all 5 specialized Phase 9 agents."""
        return [profile.to_dict() for profile in AGENT_PROFILES.values()]

    def list_runs(self, db: Session, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent agent mission executions from SQLite."""
        rows = (
            db.query(AgentRunEntry)
            .order_by(AgentRunEntry.id.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
        return [self._serialize_entry(row) for row in rows]

    def _serialize_entry(self, row: AgentRunEntry) -> dict[str, Any]:
        try:
            steps = json.loads(row.steps_json) if row.steps_json else []
        except json.JSONDecodeError:
            steps = []
        name = AGENT_PROFILES[row.agent_type].name if row.agent_type in AGENT_PROFILES else row.agent_type
        return {
            "id": row.id,
            "agent_type": row.agent_type,
            "agent_name": name,
            "goal": row.goal,
            "status": row.status,
            "steps": steps,
            "summary": row.summary,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    async def run_mission(
        self,
        db: Session,
        goal: str,
        agent_type: str | None = None,
        max_steps: int = 4,
    ) -> AgentRunResult:
        """Run a multi-step mission under the chosen or inferred specialized agent."""
        clean_goal = goal.strip()
        if not clean_goal:
            raise ValueError("Objetivo da missão não pode estar vazio.")

        resolved_type = agent_type.strip().lower() if agent_type else infer_agent_type(clean_goal)
        profile = get_agent_profile(resolved_type)
        capped_steps = max(1, min(max_steps, 6))

        entry = AgentRunEntry(
            agent_type=profile.id,
            goal=clean_goal,
            status="running",
            steps_json="[]",
            summary="",
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        steps: list[dict[str, Any]] = []
        await event_bus.set_state(AssistantState.EXECUTING, reason=f"agent.{profile.id}")
        await event_bus.emit(
            "agent.started",
            {"run_id": entry.id, "agent_type": profile.id, "agent_name": profile.name, "goal": clean_goal},
        )

        snapshot = get_system_snapshot()
        scoped_catalog = tool_registry.build_prompt_catalog(names=set(profile.allowed_tools))
        system_prompt = (
            f"{build_jarvis_system_prompt(snapshot, tools_catalog=scoped_catalog)}\n\n"
            f"=== IDENTIDADE DO AGENTE ESPECIALIZADO ({profile.name}) ===\n"
            f"{profile.instructions}\n"
            f"Tens no máximo {capped_steps} passos de ferramenta. Quando tiveres informação suficiente, "
            "responde em português natural e objetivo (sem tags <tool_call>) com o relatório final da missão."
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"Missão atribuída ao {profile.name}: {clean_goal}"),
        ]

        final_status = "completed"
        final_summary = ""

        try:
            for step_idx in range(1, capped_steps + 1):
                reply_text, provider, model, _ = await ai_manager.generate_chat(
                    db=db, messages=messages
                )
                parsed = extract_tool_call(reply_text)
                if parsed is None:
                    final_summary = reply_text.strip()
                    steps.append(
                        {
                            "step": step_idx,
                            "action": "conclusão",
                            "status": "completed",
                            "detail": f"Síntese via {provider}/{model}",
                        }
                    )
                    await event_bus.emit(
                        "agent.step",
                        {"run_id": entry.id, "agent_type": profile.id, "step": steps[-1]},
                    )
                    break

                if parsed.tool not in profile.allowed_tools:
                    step_rec = {
                        "step": step_idx,
                        "action": parsed.tool,
                        "status": "blocked",
                        "detail": f"Ferramenta fora do âmbito do {profile.name}.",
                    }
                    steps.append(step_rec)
                    await event_bus.emit(
                        "agent.step",
                        {"run_id": entry.id, "agent_type": profile.id, "step": step_rec},
                    )
                    messages.append(ChatMessage(role="assistant", content=reply_text))
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                f"A ferramenta '{parsed.tool}' não pertence a este agente ({profile.id}). "
                                f"Usa apenas {', '.join(profile.allowed_tools)} ou conclui agora com base no que já recolheste."
                            ),
                        )
                    )
                    continue

                outcome = await tool_registry.invoke(
                    db=db,
                    tool_name=parsed.tool,
                    params=parsed.args,
                )

                if outcome.status == "awaiting_confirmation":
                    final_status = "awaiting_confirmation"
                    final_summary = outcome.message
                    step_rec = {
                        "step": step_idx,
                        "action": parsed.tool,
                        "status": "awaiting_confirmation",
                        "detail": outcome.message,
                    }
                    steps.append(step_rec)
                    await event_bus.emit(
                        "agent.step",
                        {"run_id": entry.id, "agent_type": profile.id, "step": step_rec},
                    )
                    break

                if outcome.status == "blocked":
                    step_rec = {
                        "step": step_idx,
                        "action": parsed.tool,
                        "status": "blocked",
                        "detail": outcome.message,
                    }
                    steps.append(step_rec)
                    await event_bus.emit(
                        "agent.step",
                        {"run_id": entry.id, "agent_type": profile.id, "step": step_rec},
                    )
                    tool_payload: dict[str, Any] = {"success": False, "error": outcome.message}
                else:
                    tool_payload = (
                        outcome.result.model_dump()
                        if outcome.result
                        else {"success": False, "error": outcome.message}
                    )
                    step_rec = {
                        "step": step_idx,
                        "action": parsed.tool,
                        "status": "executed" if tool_payload.get("success", True) else "failed",
                        "detail": (
                            str(tool_payload.get("summary") or tool_payload.get("error") or parsed.args)[:180]
                        ),
                    }
                    steps.append(step_rec)
                    await event_bus.emit(
                        "agent.step",
                        {"run_id": entry.id, "agent_type": profile.id, "step": step_rec},
                    )

                messages.append(ChatMessage(role="assistant", content=reply_text))
                messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            f"Resultado real da ferramenta '{parsed.tool}': {json.dumps(tool_payload, ensure_ascii=False)[:3500]}. "
                            "Continua a missão ou escreve já o relatório final em português natural."
                        ),
                    )
                )
            else:
                # Reached max tool steps: ask for concise synthesis without tools
                messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "Limite de passos atingido. Apresenta agora o resumo final em português "
                            "apenas com os factos reais recolhidos, sem chamadas <tool_call>."
                        ),
                    )
                )
                reply_text, _, _, _ = await ai_manager.generate_chat(db=db, messages=messages)
                final_summary = reply_text.strip()

        except AIProviderError as exc:
            final_status = "failed"
            final_summary = exc.message
            logger.warning("Falha de IA na missão do agente %s: %s", profile.id, exc.message)
        except Exception as exc:  # noqa: BLE001
            final_status = "failed"
            final_summary = str(exc)
            logger.exception("Erro inesperado no agente %s: %s", profile.id, exc)
        finally:
            entry.status = final_status
            entry.steps_json = json.dumps(steps, ensure_ascii=False)
            entry.summary = final_summary
            entry.completed_at = utcnow()
            db.commit()
            db.refresh(entry)
            await event_bus.set_state(AssistantState.IDLE, reason=f"agent.{final_status}")

        result = AgentRunResult(
            id=entry.id,
            agent_type=profile.id,
            agent_name=profile.name,
            goal=entry.goal,
            status=entry.status,
            steps=steps,
            summary=entry.summary,
            created_at=entry.created_at.isoformat() if entry.created_at else "",
            completed_at=entry.completed_at.isoformat() if entry.completed_at else None,
        )
        await event_bus.emit("agent.completed", result.to_dict())
        if result.status in ("completed", "awaiting_confirmation") and result.summary:
            await desktop_service.notify(
                f"{result.agent_name} ({result.status})",
                result.summary[:200],
                urgency="normal",
            )
        return result


agent_orchestrator = AgentOrchestrator()
