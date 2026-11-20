"""Tool registry enforcing permissions, approval workflow, events, and audit logging."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.events import AssistantState, EventType, event_bus
from app.security.audit import record_action_log
from app.security.permissions import (
    PendingApproval,
    PermissionLevel,
    SecurityPolicy,
    SecurityViolation,
    security_policy,
)
from app.tools.app_tools import ListAppsTool, OpenApplicationTool
from app.tools.automation_tools import (
    AnalyzeProjectTool,
    CreateAgendaEventTool,
    CreateTaskTool,
    ListTasksTool,
    RunProjectTestsTool,
    WebSearchTool,
)
from app.tools.base import JarvisTool, ToolResult
from app.tools.coding_tools import GitStatusTool
from app.tools.file_tools import (
    CreateFileTool,
    ListFilesTool,
    ReadFileTool,
    SearchFilesTool,
)
from app.tools.memory_tools import SaveMemoryTool, SearchMemoryTool
from app.tools.system_tools import CheckServiceTool, SystemStatusTool
from app.tools.vision_tools import LookCameraTool
from app.tools.agent_tools import DelegateAgentTool


@dataclass
class ToolExecutionOutcome:
    """Result of dispatching a tool through the security-checked registry."""

    status: str  # executed | awaiting_confirmation | blocked | failed
    tool_name: str
    permission_level: PermissionLevel
    result: ToolResult | None = None
    approval: PendingApproval | None = None
    message: str = ""


class ToolRegistry:
    """Central registry of authorized tools with Level 1-3 security enforcement."""

    def __init__(self, policy: SecurityPolicy | None = None) -> None:
        self.policy = policy or security_policy
        self._tools: Dict[str, JarvisTool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        tools: List[JarvisTool] = [
            SystemStatusTool(),
            CheckServiceTool(self.policy),
            ListFilesTool(self.policy),
            SearchFilesTool(self.policy),
            ReadFileTool(self.policy),
            CreateFileTool(self.policy),
            ListAppsTool(),
            OpenApplicationTool(self.policy),
            GitStatusTool(self.policy),
            SearchMemoryTool(),
            SaveMemoryTool(),
            AnalyzeProjectTool(self.policy),
            RunProjectTestsTool(self.policy),
            WebSearchTool(),
            CreateTaskTool(),
            ListTasksTool(),
            CreateAgendaEventTool(),
            LookCameraTool(),
            DelegateAgentTool(),
        ]
        for tool in tools:
            self._tools[tool.name] = tool

    def list_tools(self) -> List[Dict[str, object]]:
        """Return metadata for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters_hint": t.parameters_hint,
                "permission_level": int(t.permission_level),
            }
            for t in self._tools.values()
        ]

    def build_prompt_catalog(self, names: set[str] | None = None) -> str:
        """Render a compact tool catalog for the AI system prompt."""
        tools = [
            t for t in self._tools.values() if names is None or t.name in names
        ]
        lines = [
            f"- {t.name} (Nível {int(t.permission_level)}): {t.description} Args: {t.parameters_hint}"
            for t in tools
        ]
        return "\n".join(lines)

    async def invoke(
        self,
        db: Session,
        tool_name: str,
        params: Dict[str, Any] | None = None,
        bypass_confirmation: bool = False,
    ) -> ToolExecutionOutcome:
        """Validate, authorize, and execute (or queue for approval) a tool call."""
        clean_params = params or {}
        tool = self._tools.get(tool_name)
        if tool is None:
            record_action_log(
                db,
                action_type=f"tool.{tool_name}",
                target=tool_name,
                permission_level=PermissionLevel.RESTRICTED,
                status="blocked",
                details="Ferramenta desconhecida.",
            )
            return ToolExecutionOutcome(
                status="blocked",
                tool_name=tool_name,
                permission_level=PermissionLevel.RESTRICTED,
                message=f"Ferramenta '{tool_name}' não registada.",
            )

        target = tool.describe_target(clean_params)

        # Level 3 safety pre-check across parameter values
        try:
            serialized = json.dumps(clean_params, ensure_ascii=False)
            self.policy.validate_text_command_safety(serialized)
            if tool.name == "save_memory":
                from app.memory.service import contains_sensitive_secret

                if contains_sensitive_secret(str(clean_params.get("content", ""))):
                    raise SecurityViolation(
                        "Bloqueado por segurança: passwords, tokens e API Keys nunca são guardados na memória.",
                        level=PermissionLevel.RESTRICTED,
                    )
            if tool.permission_level == PermissionLevel.RESTRICTED:
                raise SecurityViolation(
                    f"Ferramenta '{tool.name}' requer autorização especial de Nível 3.",
                    level=PermissionLevel.RESTRICTED,
                )
        except SecurityViolation as exc:
            record_action_log(
                db,
                action_type=f"tool.{tool.name}",
                target=target,
                permission_level=int(exc.level),
                status="blocked",
                details=exc.reason,
            )
            await event_bus.emit(
                EventType.TOOL_FAILED.value,
                {"tool": tool.name, "target": target, "error": exc.reason},
            )
            return ToolExecutionOutcome(
                status="blocked",
                tool_name=tool.name,
                permission_level=exc.level,
                message=exc.reason,
            )

        # Level 2 confirmation gate
        if (
            tool.permission_level == PermissionLevel.CONFIRMATION_REQUIRED
            and self.policy.settings.require_confirmation_level_2
            and not bypass_confirmation
        ):
            # Validate path safety before asking for confirmation so invalid/credential paths are blocked upfront
            if "path" in clean_params:
                try:
                    self.policy.validate_authorized_path(
                        str(clean_params["path"]), allow_nonexistent=True
                    )
                except SecurityViolation as exc:
                    record_action_log(
                        db,
                        action_type=f"tool.{tool.name}",
                        target=target,
                        permission_level=int(exc.level),
                        status="blocked",
                        details=exc.reason,
                    )
                    return ToolExecutionOutcome(
                        status="blocked",
                        tool_name=tool.name,
                        permission_level=exc.level,
                        message=exc.reason,
                    )

            approval = self.policy.create_pending_approval(
                tool_name=tool.name,
                target=target,
                params=clean_params,
                description=tool.description,
            )
            record_action_log(
                db,
                action_type=f"tool.{tool.name}",
                target=target,
                permission_level=int(tool.permission_level),
                status="awaiting_confirmation",
                details={"approval_id": approval.id, "params": clean_params},
            )
            await event_bus.emit(
                "tool.approval_required",
                {
                    "approval_id": approval.id,
                    "tool": approval.tool_name,
                    "target": approval.target,
                    "description": approval.description,
                    "permission_level": int(approval.permission_level),
                    "params": approval.params,
                },
            )
            await event_bus.emit(
                EventType.NOTIFICATION_CREATED.value,
                {
                    "title": "Confirmação necessária (Nível 2)",
                    "message": f"Autorizar {approval.tool_name} em '{approval.target}'?",
                },
            )
            return ToolExecutionOutcome(
                status="awaiting_confirmation",
                tool_name=tool.name,
                permission_level=tool.permission_level,
                approval=approval,
                message=f"Ação '{tool.name}' em '{target}' aguarda confirmação explícita (Nível 2).",
            )

        # Execute tool safely
        await event_bus.set_state(AssistantState.EXECUTING, reason=f"tool:{tool.name}")
        await event_bus.emit(
            EventType.TOOL_STARTED.value,
            {"tool": tool.name, "target": target},
        )
        result = await tool.execute_with_db(db, clean_params)

        if result.success:
            record_action_log(
                db,
                action_type=f"tool.{tool.name}",
                target=target,
                permission_level=int(tool.permission_level),
                status="executed",
                details=result.output,
            )
            await event_bus.emit(
                EventType.TOOL_COMPLETED.value,
                {"tool": tool.name, "target": target, "output": result.output},
            )
            return ToolExecutionOutcome(
                status="executed",
                tool_name=tool.name,
                permission_level=tool.permission_level,
                result=result,
            )

        record_action_log(
            db,
            action_type=f"tool.{tool.name}",
            target=target,
            permission_level=int(tool.permission_level),
            status="failed",
            details=result.error or "Erro desconhecido.",
        )
        await event_bus.emit(
            EventType.TOOL_FAILED.value,
            {"tool": tool.name, "target": target, "error": result.error},
        )
        return ToolExecutionOutcome(
            status="failed",
            tool_name=tool.name,
            permission_level=tool.permission_level,
            result=result,
            message=result.error or "Falha ao executar ferramenta.",
        )

    async def approve_pending(self, db: Session, approval_id: str) -> ToolExecutionOutcome:
        """Authorize and execute a pending Level 2 action."""
        approval = self.policy.pop_pending_approval(approval_id)
        if approval is None:
            return ToolExecutionOutcome(
                status="failed",
                tool_name="unknown",
                permission_level=PermissionLevel.CONFIRMATION_REQUIRED,
                message="Pedido de aprovação não encontrado ou expirado.",
            )
        outcome = await self.invoke(
            db=db,
            tool_name=approval.tool_name,
            params=approval.params,
            bypass_confirmation=True,
        )
        await event_bus.set_state(AssistantState.IDLE, reason="tool_approved")
        return outcome

    async def reject_pending(self, db: Session, approval_id: str) -> PendingApproval | None:
        """Cancel a pending Level 2 action and record the rejection."""
        approval = self.policy.pop_pending_approval(approval_id)
        if approval is None:
            return None
        record_action_log(
            db,
            action_type=f"tool.{approval.tool_name}",
            target=approval.target,
            permission_level=int(approval.permission_level),
            status="rejected",
            details={"approval_id": approval.id},
        )
        await event_bus.emit(
            "tool.rejected",
            {"approval_id": approval.id, "tool": approval.tool_name, "target": approval.target},
        )
        await event_bus.set_state(AssistantState.IDLE, reason="tool_rejected")
        return approval


tool_registry = ToolRegistry()
