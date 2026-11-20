"""System telemetry, rolling history, and configurable alert endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.system.alerts import AlertConfig, alert_engine
from app.system.telemetry import get_system_history, get_system_snapshot

router = APIRouter(prefix="/system", tags=["system"])


class AlertConfigPayload(BaseModel):
    """Configurable system monitoring alert thresholds."""

    enabled: bool = True
    cpu_threshold: float = Field(default=88.0, ge=20.0, le=100.0)
    ram_threshold: float = Field(default=85.0, ge=20.0, le=100.0)
    disk_threshold: float = Field(default=95.0, ge=30.0, le=100.0)
    temp_threshold: float = Field(default=82.0, ge=40.0, le=110.0)
    cooldown_seconds: int = Field(default=300, ge=10, le=3600)


@router.get("/status")
async def read_system_status() -> dict[str, object]:
    """Return real-time CPU, RAM, disk, network throughput, and host information."""
    return get_system_snapshot()


@router.get("/history")
async def read_system_history() -> dict[str, object]:
    """Return recent rolling telemetry points for live charts."""
    return {"points": get_system_history()}


@router.get("/alerts/config")
def read_alert_config(db: Session = Depends(get_db)) -> dict[str, object]:
    """Return active alert threshold configuration."""
    return asdict(alert_engine.get_config(db))


@router.put("/alerts/config")
def update_alert_config(
    payload: AlertConfigPayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Update and persist configurable alert thresholds."""
    updated = alert_engine.update_config(
        db,
        AlertConfig(
            enabled=payload.enabled,
            cpu_threshold=payload.cpu_threshold,
            ram_threshold=payload.ram_threshold,
            disk_threshold=payload.disk_threshold,
            temp_threshold=payload.temp_threshold,
            cooldown_seconds=payload.cooldown_seconds,
        ),
    )
    return asdict(updated)
