"""Level 1 delegation tool allowing Muquissi voice/chat to launch specialized Phase 9 agents."""

from __future__ import annotations

from typing import Any, Dict

from app.database.session import SessionLocal
from app.security.permissions import PermissionLevel
from app.tools.base import JarvisTool, ToolResult


class DelegateAgentTool(JarvisTool):
    """Delegates a multi-step mission to a specialized Phase 9 sub-agent."""

    name = "delegate_agent"
    description = (
        "Delega uma missão multi-passo para um agente especializado "
        "(coding, system, research, automation ou project)."
    )
    parameters_hint = '{"agent_type": "coding|system|research|automation|project", "goal": "objetivo claro"}'
    permission_level = PermissionLevel.SAFE

    def describe_target(self, params: Dict[str, Any]) -> str:
        agent = str(params.get("agent_type") or "auto")
        goal = str(params.get("goal") or "")[:60]
        return f"{agent}: {goal}"

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        from app.agents import agent_orchestrator

        goal = str(params.get("goal") or "").strip()
        if not goal:
            return ToolResult(success=False, error="Indica 'goal' para o agente executar.")

        raw_type = params.get("agent_type")
        agent_type = str(raw_type).strip().lower() if raw_type else None

        db = SessionLocal()
        try:
            outcome = await agent_orchestrator.run_mission(
                db=db,
                goal=goal,
                agent_type=agent_type,
                max_steps=4,
            )
            return ToolResult(
                success=outcome.status in ("completed", "awaiting_confirmation"),
                data=outcome.to_dict(),
            )
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        finally:
            db.close()
