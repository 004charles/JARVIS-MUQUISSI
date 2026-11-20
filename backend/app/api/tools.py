"""Tools inspection, Level 2 approvals, and security audit endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.security.audit import list_action_logs
from app.tools.registry import ToolRegistry, tool_registry

router = APIRouter(prefix="/tools", tags=["tools"])


def get_tool_registry() -> ToolRegistry:
    """Dependency returning the active ToolRegistry."""
    return tool_registry


class ExecuteToolRequest(BaseModel):
    """Direct tool execution request payload."""

    params: Dict[str, Any] = {}


@router.get("")
def list_registered_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    """List all registered tools with permission levels and allowed directories."""
    return {
        "tools": registry.list_tools(),
        "allowed_directories": [str(p) for p in registry.policy.allowed_directories],
        "require_confirmation_level_2": registry.policy.settings.require_confirmation_level_2,
    }


@router.get("/logs")
def get_action_logs(
    limit: int = 40,
    db: Session = Depends(get_db),
) -> List[dict[str, object]]:
    """Return recent security/tool audit logs from SQLite."""
    safe_limit = min(max(limit, 1), 200)
    rows = list_action_logs(db, limit=safe_limit)
    return [
        {
            "id": row.id,
            "action_type": row.action_type,
            "target": row.target,
            "permission_level": row.permission_level,
            "status": row.status,
            "details": row.details,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/approvals")
def list_pending_approvals(
    registry: ToolRegistry = Depends(get_tool_registry),
) -> List[dict[str, object]]:
    """List pending Level 2 tool actions waiting for user confirmation."""
    return [
        {
            "approval_id": item.id,
            "tool": item.tool_name,
            "target": item.target,
            "description": item.description,
            "permission_level": int(item.permission_level),
            "params": item.params,
            "created_at": item.created_at.isoformat(),
            "expires_at": item.expires_at.isoformat(),
        }
        for item in registry.policy.list_pending_approvals()
    ]


@router.post("/{tool_name}/execute")
async def execute_tool_endpoint(
    tool_name: str,
    payload: ExecuteToolRequest,
    db: Session = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    """Invoke a tool through the security policy and permission gate."""
    outcome = await registry.invoke(db=db, tool_name=tool_name, params=payload.params)
    return {
        "status": outcome.status,
        "tool": outcome.tool_name,
        "permission_level": int(outcome.permission_level),
        "message": outcome.message,
        "result": outcome.result.model_dump() if outcome.result else None,
        "approval_id": outcome.approval.id if outcome.approval else None,
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_pending_action(
    approval_id: str,
    db: Session = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    """Approve and execute a pending Level 2 action."""
    outcome = await registry.approve_pending(db=db, approval_id=approval_id)
    if outcome.tool_name == "unknown":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=outcome.message,
        )
    return {
        "status": outcome.status,
        "tool": outcome.tool_name,
        "message": outcome.message,
        "result": outcome.result.model_dump() if outcome.result else None,
    }


@router.post("/approvals/{approval_id}/reject")
async def reject_pending_action(
    approval_id: str,
    db: Session = Depends(get_db),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> dict[str, object]:
    """Reject and cancel a pending Level 2 action."""
    rejected = await registry.reject_pending(db=db, approval_id=approval_id)
    if rejected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido de aprovação não encontrado ou expirado.",
        )
    return {
        "status": "rejected",
        "approval_id": rejected.id,
        "tool": rejected.tool_name,
        "target": rejected.target,
    }
