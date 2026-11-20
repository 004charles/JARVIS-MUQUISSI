"""Tool contract with mandatory permission level declaration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.security.permissions import PermissionLevel


class ToolResult(BaseModel):
    """Structured result produced by any J.A.R.V.I.S. tool."""

    success: bool
    output: Any = None
    error: str | None = None


class JarvisTool(ABC):
    """Base contract for every controlled system tool."""

    name: str
    description: str
    parameters_hint: str = "{}"
    permission_level: PermissionLevel = PermissionLevel.SAFE

    def describe_target(self, params: Dict[str, Any]) -> str:
        """Return a concise human-readable target for audit logs and approvals."""
        for key in ("path", "directory", "app", "service", "query"):
            if key in params and params[key]:
                return str(params[key])
        return self.name

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Validate parameters and run the tool safely."""

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        """Execute tool with access to the active database session when needed."""
        _ = db
        return await self.execute(params)
