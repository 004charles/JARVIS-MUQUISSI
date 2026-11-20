"""Persistent notification history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database.models import NotificationEntry
from app.database.session import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    limit: int = 30,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """List recent persistent notifications and unread count."""
    safe_limit = min(max(limit, 1), 100)
    rows = list(
        db.scalars(
            select(NotificationEntry)
            .order_by(NotificationEntry.id.desc())
            .limit(safe_limit)
        ).all()
    )
    unread_count = db.scalar(
        select(func.count()).select_from(NotificationEntry).where(NotificationEntry.read.is_(False))
    )
    return {
        "unread_count": int(unread_count or 0),
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "message": row.message,
                "severity": row.severity,
                "source": row.source,
                "read": row.read,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Mark a single notification as read."""
    entry = db.get(NotificationEntry, notification_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada.",
        )
    entry.read = True
    db.commit()
    return {"id": entry.id, "read": True}


@router.post("/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db)) -> dict[str, object]:
    """Mark all unread notifications as read."""
    db.execute(update(NotificationEntry).where(NotificationEntry.read.is_(False)).values(read=True))
    db.commit()
    return {"unread_count": 0}
