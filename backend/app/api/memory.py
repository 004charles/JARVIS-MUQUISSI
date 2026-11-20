"""Memory management, search, and operational history REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.memory.service import SensitiveMemoryError, memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreateRequest(BaseModel):
    """Payload to store a user-approved persistent memory."""

    category: str = Field(default="long_term", max_length=40)
    content: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="user", max_length=100)
    approved: bool = True


class MemoryUpdateRequest(BaseModel):
    """Payload to update or approve an existing memory."""

    category: str | None = Field(default=None, max_length=40)
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    approved: bool | None = None


def _serialize_memory(entry) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "id": entry.id,
        "category": entry.category,
        "content": entry.content,
        "source": entry.source,
        "approved": entry.approved,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


@router.get("")
def list_memories(
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    approved_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """List searchable persistent memories and recent operational actions."""
    items = memory_service.list_memories(
        db=db,
        category=category,
        query=q,
        approved_only=approved_only,
    )
    operational = memory_service.list_operational_history(db=db, limit=25)
    return {
        "items": [_serialize_memory(item) for item in items],
        "operational": operational,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create a persistent memory entry (rejects secrets/credentials)."""
    try:
        entry = memory_service.create_memory(
            db=db,
            category=payload.category,
            content=payload.content,
            source=payload.source,
            approved=payload.approved,
        )
    except (SensitiveMemoryError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _serialize_memory(entry)


@router.put("/{memory_id}")
def update_memory(
    memory_id: int,
    payload: MemoryUpdateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update or approve an existing memory entry."""
    try:
        entry = memory_service.update_memory(
            db=db,
            memory_id=memory_id,
            content=payload.content,
            category=payload.category,
            approved=payload.approved,
        )
    except (SensitiveMemoryError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memória não encontrada.",
        )
    return _serialize_memory(entry)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Delete a memory entry permanently."""
    deleted = memory_service.delete_memory(db=db, memory_id=memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memória não encontrada.",
        )
    return {"deleted": True, "id": memory_id}
