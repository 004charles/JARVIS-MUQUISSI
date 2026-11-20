"""Real-time event definitions and async WebSocket event bus."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Set

from fastapi import WebSocket
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger("events")


class AssistantState(str, Enum):
    """Visual and operational states of the J.A.R.V.I.S. core."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    EXECUTING = "executing"
    ERROR = "error"


class EventType(str, Enum):
    """Standardized real-time events broadcast between backend and frontend."""

    ASSISTANT_IDLE = "assistant.idle"
    ASSISTANT_LISTENING = "assistant.listening"
    ASSISTANT_PROCESSING = "assistant.processing"
    ASSISTANT_SPEAKING = "assistant.speaking"
    ASSISTANT_EXECUTING = "assistant.executing"
    ASSISTANT_ERROR = "assistant.error"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    SYSTEM_UPDATED = "system.updated"
    NOTIFICATION_CREATED = "notification.created"
    CONNECTION_READY = "connection.ready"


class JarvisEvent(BaseModel):
    """Envelope for real-time events sent over WebSocket."""

    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EventBus:
    """Manages active WebSocket clients and broadcasts structured events."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._state: AssistantState = AssistantState.IDLE
        self._lock = asyncio.Lock()

    @property
    def state(self) -> AssistantState:
        """Current assistant core state."""
        return self._state

    @property
    def connection_count(self) -> int:
        """Number of active WebSocket clients."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("WebSocket ligado (clientes ativos: %d)", len(self._connections))
        await self.send_to(
            websocket,
            JarvisEvent(
                type=EventType.CONNECTION_READY.value,
                payload={"state": self._state.value, "clients": len(self._connections)},
            ),
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info("WebSocket desligado (clientes ativos: %d)", len(self._connections))

    async def send_to(self, websocket: WebSocket, event: JarvisEvent) -> None:
        """Send an event to a single WebSocket client."""
        await websocket.send_json(event.model_dump())

    async def emit(self, event_type: str, payload: Dict[str, Any] | None = None) -> None:
        """Broadcast an event to all connected WebSocket clients."""
        event = JarvisEvent(type=event_type, payload=payload or {})
        async with self._lock:
            targets = list(self._connections)

        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(event.model_dump())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao enviar evento para cliente WS: %s", exc)
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)

    async def set_state(self, state: AssistantState, reason: str | None = None) -> None:
        """Update assistant state and emit the corresponding assistant.* event."""
        self._state = state
        await self.emit(
            f"assistant.{state.value}",
            {"state": state.value, "reason": reason},
        )


event_bus = EventBus()
