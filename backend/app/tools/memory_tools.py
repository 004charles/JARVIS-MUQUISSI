"""Memory lookup (Level 1) and confirmation-gated memory storage (Level 2) tools."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.memory.service import SensitiveMemoryError, memory_service
from app.security.permissions import PermissionLevel
from app.tools.base import JarvisTool, ToolResult


class SearchMemoryTool(JarvisTool):
    """Search authorized long-term and project memories (Level 1 Safe)."""

    name = "search_memory"
    description = "Pesquisar memórias aprovadas (longo prazo, projetos e preferências)."
    parameters_hint = '{"query": "texto-de-pesquisa"}'
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        query = str(params.get("query", "")).strip()
        entries = memory_service.search_relevant_memories(db, query=query, limit=10)
        return ToolResult(
            success=True,
            output={
                "matches": [
                    {
                        "id": e.id,
                        "category": e.category,
                        "content": e.content,
                        "source": e.source,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in entries
                ]
            },
        )


class SaveMemoryTool(JarvisTool):
    """Persist a new long-term or project memory (Level 2 Requires Confirmation)."""

    name = "save_memory"
    description = "Guardar uma informação importante na memória persistente (requer confirmação do Carlos)."
    parameters_hint = '{"category": "long_term|project|preference", "content": "informacao"}'
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED

    def describe_target(self, params: Dict[str, Any]) -> str:
        category = str(params.get("category", "long_term"))
        content = str(params.get("content", "")).strip()
        return f"{category}: {content[:60]}"

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        category = str(params.get("category", "long_term")).strip()
        content = str(params.get("content", "")).strip()
        try:
            entry = memory_service.create_memory(
                db=db,
                category=category,
                content=content,
                source="assistant_confirmed",
                approved=True,
            )
            return ToolResult(
                success=True,
                output={
                    "id": entry.id,
                    "category": entry.category,
                    "content": entry.content,
                    "created_at": entry.created_at.isoformat(),
                },
            )
        except (SensitiveMemoryError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))
