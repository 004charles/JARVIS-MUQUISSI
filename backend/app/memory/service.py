"""Controlled multi-layer memory service with secret filtering and search."""

from __future__ import annotations

import re
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ActionLog, MemoryEntry

VALID_MEMORY_CATEGORIES = {"long_term", "project", "preference", "operational"}

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bAQ\.[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(password|passwd|senha|api[_\s-]?key|secret[_\s-]?key|access[_\s-]?token)\s*[:=]\s*\S+"
    ),
)


class SensitiveMemoryError(ValueError):
    """Raised when attempting to persist secrets, passwords, tokens, or API keys."""


def contains_sensitive_secret(text: str) -> bool:
    """Detect credentials, passwords, or API tokens that must never be stored."""
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


class MemoryService:
    """Manages long-term, project, preference, and operational memories in SQLite."""

    def create_memory(
        self,
        db: Session,
        category: str,
        content: str,
        source: str = "user",
        approved: bool = True,
    ) -> MemoryEntry:
        """Validate and persist a memory entry while rejecting any secret material."""
        clean_cat = category.strip().lower()
        if clean_cat not in VALID_MEMORY_CATEGORIES:
            raise ValueError(
                f"Categoria inválida '{category}'. Opções: {', '.join(sorted(VALID_MEMORY_CATEGORIES))}"
            )
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Conteúdo da memória não pode estar vazio.")
        if contains_sensitive_secret(clean_content):
            raise SensitiveMemoryError(
                "Bloqueado por segurança: passwords, tokens e API Keys nunca são guardados na memória."
            )

        entry = MemoryEntry(
            category=clean_cat,
            content=clean_content,
            source=source.strip() or "user",
            approved=approved,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def list_memories(
        self,
        db: Session,
        category: str | None = None,
        query: str | None = None,
        approved_only: bool = False,
        limit: int = 100,
    ) -> List[MemoryEntry]:
        """List memories filtered by category, approval state, and search text."""
        stmt = select(MemoryEntry)
        if category and category != "all":
            stmt = stmt.where(MemoryEntry.category == category)
        if approved_only:
            stmt = stmt.where(MemoryEntry.approved.is_(True))
        if query and query.strip():
            needle = f"%{query.strip()}%"
            stmt = stmt.where(MemoryEntry.content.ilike(needle))
        stmt = stmt.order_by(MemoryEntry.updated_at.desc(), MemoryEntry.id.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def update_memory(
        self,
        db: Session,
        memory_id: int,
        content: str | None = None,
        category: str | None = None,
        approved: bool | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory entry after re-validating safety."""
        entry = db.get(MemoryEntry, memory_id)
        if entry is None:
            return None

        if content is not None:
            clean = content.strip()
            if not clean:
                raise ValueError("Conteúdo da memória não pode estar vazio.")
            if contains_sensitive_secret(clean):
                raise SensitiveMemoryError(
                    "Bloqueado por segurança: passwords, tokens e API Keys nunca são guardados na memória."
                )
            entry.content = clean

        if category is not None:
            clean_cat = category.strip().lower()
            if clean_cat not in VALID_MEMORY_CATEGORIES:
                raise ValueError(f"Categoria inválida: {category}")
            entry.category = clean_cat

        if approved is not None:
            entry.approved = approved

        db.commit()
        db.refresh(entry)
        return entry

    def delete_memory(self, db: Session, memory_id: int) -> bool:
        """Remove a memory entry permanently."""
        entry = db.get(MemoryEntry, memory_id)
        if entry is None:
            return False
        db.delete(entry)
        db.commit()
        return True

    def search_relevant_memories(
        self, db: Session, query: str, limit: int = 8
    ) -> List[MemoryEntry]:
        """Rank approved long-term/project memories by keyword overlap and recency."""
        all_approved = self.list_memories(db, approved_only=True, limit=80)
        if not all_approved:
            return []

        tokens = {
            tok
            for tok in re.findall(r"[a-zA-Z0-9À-ÿ]{3,}", query.lower())
        }
        if not tokens:
            return all_approved[:limit]

        scored: list[tuple[int, int, MemoryEntry]] = []
        for idx, item in enumerate(all_approved):
            item_lower = item.content.lower()
            hits = sum(1 for tok in tokens if tok in item_lower)
            # Prioritize keyword matches while keeping newest general context
            scored.append((hits, -idx, item))

        scored.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
        return [item for _hits, _neg_idx, item in scored[:limit]]

    def list_operational_history(self, db: Session, limit: int = 25) -> List[Dict[str, object]]:
        """Expose recent executed system actions as operational memory."""
        stmt = select(ActionLog).order_by(ActionLog.id.desc()).limit(limit)
        rows = list(db.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "action_type": r.action_type,
                "target": r.target,
                "permission_level": r.permission_level,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


memory_service = MemoryService()
