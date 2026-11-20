"""Database audit trail for tool executions, approvals, and blocked operations."""

from __future__ import annotations

import json
from typing import Any, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ActionLog


def record_action_log(
    db: Session,
    action_type: str,
    target: str,
    permission_level: int,
    status: str,
    details: Any = "",
) -> ActionLog:
    """Persist an auditable action event into SQLite `action_logs`."""
    serialized = (
        details
        if isinstance(details, str)
        else json.dumps(details, ensure_ascii=False, default=str)
    )
    entry = ActionLog(
        action_type=action_type,
        target=target[:255],
        permission_level=permission_level,
        status=status,
        details=serialized[:4000],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_action_logs(db: Session, limit: int = 50) -> List[ActionLog]:
    """Return recent action audit entries ordered newest first."""
    stmt = select(ActionLog).order_by(ActionLog.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())
