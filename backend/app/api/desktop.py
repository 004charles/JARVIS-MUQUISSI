"""Phase 10 Ubuntu desktop integration endpoints: status, autostart, launcher, notifications."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.desktop import UrgencyLevel, desktop_service

router = APIRouter(prefix="/desktop", tags=["desktop"])


class TogglePayload(BaseModel):
    """Enable/disable desktop integration flag."""

    enabled: bool


class DesktopNotifyRequest(BaseModel):
    """Send a native Ubuntu notification."""

    title: str = Field(default="Arcanjo", min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=300)
    urgency: UrgencyLevel = "normal"


@router.get("/status")
async def get_desktop_status() -> dict[str, object]:
    """Return Ubuntu desktop integration, launcher, autostart, and notification status."""
    return desktop_service.status()


@router.put("/autostart")
async def update_desktop_autostart(payload: TogglePayload) -> dict[str, object]:
    """Enable or disable Ubuntu autostart entry."""
    return desktop_service.set_autostart(payload.enabled)


@router.put("/notifications")
async def update_desktop_notifications(payload: TogglePayload) -> dict[str, object]:
    """Enable or disable native Ubuntu desktop notifications."""
    desktop_service.notifications_enabled = payload.enabled
    return desktop_service.status()


@router.post("/install-launcher")
async def install_desktop_launcher() -> dict[str, object]:
    """Install the Arcanjo `.desktop` shortcut in Ubuntu applications menu."""
    return desktop_service.install_desktop_entry()


@router.post("/notify")
async def send_desktop_notification(payload: DesktopNotifyRequest) -> dict[str, object]:
    """Trigger a native Ubuntu `notify-send` notification."""
    sent = await desktop_service.notify(
        title=payload.title,
        message=payload.message,
        urgency=payload.urgency,
    )
    return {"sent": sent, "title": payload.title, "message": payload.message}
