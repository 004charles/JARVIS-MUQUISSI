"""Health and architecture status endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.events import event_bus
from app.database.session import check_db_connection, get_db
from app.services.ollama_probe import check_ollama_status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return operational health of API, database, WebSocket bus, and local Ollama."""
    db_ok = check_db_connection(db)
    ollama_status = await check_ollama_status(settings.ollama_base_url)

    return {
        "status": "operational" if db_ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "assistant_state": event_bus.state.value,
        "websocket_clients": event_bus.connection_count,
        "database": {"connected": db_ok, "engine": "sqlite"},
        "ollama": ollama_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/info")
async def system_info(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return active phase and modular architecture readiness."""
    return {
        "name": settings.app_name,
        "meaning": "Assistente Pessoal Inteligente",
        "version": settings.app_version,
        "phase": 10,
        "phase_name": "Aplicação Desktop",
        "modules": {
            "core": "ready",
            "database": "ready",
            "websocket_events": "ready",
            "system_telemetry": "ready",
            "notifications": "ready",
            "ai_engine": "ready",
            "tools_security": "ready",
            "voice": "active_tts_stt_neural_vad",
            "vision": "ready",
            "memory": "ready",
            "automation": "ready",
            "agents": "ready",
            "desktop": "ready",
        },
        "default_ai_provider": settings.ai_default_provider,
        "voice_language": settings.voice_language,
    }
