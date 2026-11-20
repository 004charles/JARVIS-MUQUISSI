"""FastAPI application entry point for J.A.R.V.I.S."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ChatMessage
from app.ai.manager import ai_manager
from app.ai.prompts import (
    build_dynamic_greeting_prompt,
    build_jarvis_system_prompt,
    fallback_dynamic_greeting,
    remember_greeting,
)
from app.ai.tool_orchestrator import extract_tool_call
from app.api import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.events import AssistantState, EventType, JarvisEvent, event_bus
from app.core.logging import get_logger, setup_logging
from app.database.models import Conversation, Message
from app.database.session import SessionLocal, get_db, init_db
from app.system.alerts import alert_engine
from app.system.telemetry import get_system_snapshot
from app.tools.registry import tool_registry
from app.vision.service import vision_service
from app.voice.ambient_brain import ambient_brain, infer_face_mood
from app.voice.linux_listener import native_voice_service

logger = get_logger("main")


async def _telemetry_broadcaster(interval_seconds: int = 5) -> None:
    """Periodically collect telemetry, evaluate alert rules, and broadcast over WebSocket."""
    while True:
        await asyncio.sleep(interval_seconds)
        snapshot = get_system_snapshot(record_history=True)
        if "PYTEST_CURRENT_TEST" not in os.environ:
            db = SessionLocal()
            try:
                await alert_engine.evaluate(db, snapshot)
            finally:
                db.close()
        if event_bus.connection_count > 0:
            await event_bus.emit(
                EventType.SYSTEM_UPDATED.value,
                snapshot,
            )


def _open_ws_session(app: FastAPI) -> tuple[Session, Any | None]:
    """Open a DB session honoring FastAPI dependency overrides during tests."""
    override = app.dependency_overrides.get(get_db)
    if override is not None:
        gen = override()
        return next(gen), gen
    return SessionLocal(), None


def _close_ws_session(session: Session, gen: Any | None) -> None:
    """Close a WebSocket DB session or finalize its generator override."""
    if gen is not None:
        try:
            next(gen)
        except StopIteration:
            pass
    else:
        session.close()


async def _handle_ws_chat(
    app: FastAPI,
    websocket: WebSocket,
    user_text: str,
    conversation_id: int | None,
    provider_override: str | None,
    model_override: str | None,
) -> None:
    """Persist user message, stream AI reply over WebSocket, and persist assistant turn."""
    db, gen = _open_ws_session(app)
    accumulated: list[str] = []
    used_provider = ""
    used_model = ""
    fallback_used = False
    conv_id: int | None = None

    try:
        if conversation_id is not None:
            conversation = db.get(Conversation, conversation_id)
        else:
            conversation = None

        if conversation is None:
            conversation = Conversation(title=user_text[:60] or "Nova Conversa")
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

        conv_id = conversation.id
        user_msg = Message(conversation_id=conv_id, role="user", content=user_text)
        db.add(user_msg)
        db.commit()

        await event_bus.set_state(AssistantState.PROCESSING, reason="ai_streaming")
        context_messages = ai_manager.build_conversation_messages(
            db, conv_id, tools_catalog=tool_registry.build_prompt_catalog()
        )

        # Buffer leading characters briefly to detect <tool_call> before streaming text
        prefix_buffer: list[str] = []
        tool_mode: bool | None = None
        stream_started = False

        async for chunk in ai_manager.stream_chat(
            db=db,
            messages=context_messages,
            provider_override=provider_override,
            model_override=model_override,
        ):
            used_provider = chunk.provider
            used_model = chunk.model
            fallback_used = chunk.fallback_used

            if tool_mode is None:
                prefix_buffer.append(chunk.delta)
                joined = "".join(prefix_buffer).lstrip()
                if joined.startswith("<tool_call>"):
                    tool_mode = True
                    continue
                if len(joined) >= 12 or ("<" not in joined and len(joined) >= 4):
                    tool_mode = False
                    stream_started = True
                    await event_bus.set_state(AssistantState.SPEAKING, reason="ai_streaming")
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type="chat.stream.start",
                            payload={
                                "conversation_id": conv_id,
                                "provider": used_provider,
                                "model": used_model,
                                "fallback_used": fallback_used,
                            },
                        ),
                    )
                    initial_text = "".join(prefix_buffer)
                    prefix_buffer.clear()
                    accumulated.append(initial_text)
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type="chat.stream.delta",
                            payload={"conversation_id": conv_id, "delta": initial_text},
                        ),
                    )
                continue

            if tool_mode:
                prefix_buffer.append(chunk.delta)
                continue

            accumulated.append(chunk.delta)
            await event_bus.send_to(
                websocket,
                JarvisEvent(
                    type="chat.stream.delta",
                    payload={"conversation_id": conv_id, "delta": chunk.delta},
                ),
            )

        if tool_mode:
            raw_tool_text = "".join(prefix_buffer)
            parsed_call = extract_tool_call(raw_tool_text)
            if parsed_call is None:
                # Fallback: treat as regular text if malformed
                full_text = raw_tool_text.strip()
            else:
                outcome = await tool_registry.invoke(
                    db=db, tool_name=parsed_call.tool, params=parsed_call.args
                )
                if outcome.status == "awaiting_confirmation":
                    full_text = outcome.message
                elif outcome.status == "blocked":
                    full_text = f"Operação bloqueada por segurança: {outcome.message}"
                else:
                    tool_summary_payload = (
                        outcome.result.model_dump()
                        if outcome.result
                        else {"success": False, "error": outcome.message}
                    )
                    followup_messages = [
                        *context_messages,
                        ChatMessage(role="assistant", content=raw_tool_text),
                        ChatMessage(
                            role="user",
                            content=(
                                f"Resultado real da ferramenta '{parsed_call.tool}': "
                                f"{tool_summary_payload}. "
                                "Responde agora ao Carlos em português natural e conciso com base apenas nesse resultado real."
                            ),
                        ),
                    ]
                    await event_bus.set_state(AssistantState.SPEAKING, reason="ai_streaming")
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type="chat.stream.start",
                            payload={
                                "conversation_id": conv_id,
                                "provider": used_provider,
                                "model": used_model,
                                "fallback_used": fallback_used,
                            },
                        ),
                    )
                    stream_started = True
                    async for post_chunk in ai_manager.stream_chat(
                        db=db,
                        messages=followup_messages,
                        provider_override=provider_override,
                        model_override=model_override,
                    ):
                        accumulated.append(post_chunk.delta)
                        await event_bus.send_to(
                            websocket,
                            JarvisEvent(
                                type="chat.stream.delta",
                                payload={"conversation_id": conv_id, "delta": post_chunk.delta},
                            ),
                        )
                    full_text = "".join(accumulated).strip()
        else:
            if not stream_started and prefix_buffer:
                remainder = "".join(prefix_buffer)
                accumulated.append(remainder)
                await event_bus.set_state(AssistantState.SPEAKING, reason="ai_streaming")
                await event_bus.send_to(
                    websocket,
                    JarvisEvent(
                        type="chat.stream.start",
                        payload={
                            "conversation_id": conv_id,
                            "provider": used_provider,
                            "model": used_model,
                            "fallback_used": fallback_used,
                        },
                    ),
                )
                await event_bus.send_to(
                    websocket,
                    JarvisEvent(
                        type="chat.stream.delta",
                        payload={"conversation_id": conv_id, "delta": remainder},
                    ),
                )
            full_text = "".join(accumulated).strip()

        if not full_text:
            raise AIProviderError(
                used_provider or "ai",
                "O modelo não produziu conteúdo de resposta.",
            )

        if not stream_started:
            await event_bus.set_state(AssistantState.SPEAKING, reason="tool_notice")

        assistant_msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content=full_text,
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.stream.end",
                payload={
                    "conversation_id": conv_id,
                    "message_id": assistant_msg.id,
                    "role": "assistant",
                    "content": full_text,
                    "provider": used_provider,
                    "model": used_model,
                    "fallback_used": fallback_used,
                    "speak": True,
                    "mood": infer_face_mood(f"{user_text} {full_text}", get_system_snapshot()),
                },
            ),
        )
    except asyncio.CancelledError:
        partial = "".join(accumulated).strip()
        if partial and conv_id is not None:
            db.add(
                Message(
                    conversation_id=conv_id,
                    role="assistant",
                    content=f"{partial} [interrompido]",
                )
            )
            db.commit()
        await event_bus.set_state(AssistantState.IDLE, reason="interrupted")
        raise
    except AIProviderError as exc:
        logger.warning("Erro do provider IA no WebSocket: %s", exc.message)
        await event_bus.set_state(AssistantState.ERROR, reason="ai_provider_unavailable")
        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.error",
                payload={
                    "conversation_id": conv_id,
                    "provider": exc.provider,
                    "message": exc.message,
                },
            ),
        )
    finally:
        _close_ws_session(db, gen)


async def _handle_ws_ambient(
    app: FastAPI,
    websocket: WebSocket,
    user_text: str,
    conversation_id: int | None,
) -> None:
    """Evaluate browser-heard ambient conversation and speak an opinion if appropriate."""
    db, gen = _open_ws_session(app)
    try:
        decision = await ambient_brain.evaluate_and_respond(
            db=db,
            transcript=user_text,
            source="browser",
            conversation_id=conversation_id,
        )
        if decision.heard:
            await event_bus.send_to(
                websocket,
                JarvisEvent(
                    type="voice.ambient.heard",
                    payload={
                        "text": decision.cleaned_text,
                        "spoken": decision.should_speak,
                        "reason": decision.reason,
                        "mode": decision.mode,
                        "recent_heard": ambient_brain.recent_heard(6),
                        "mood": infer_face_mood(
                            f"{decision.cleaned_text} {decision.reply_text}",
                            get_system_snapshot(),
                        ),
                    },
                ),
            )

        if not decision.should_speak or not decision.reply_text:
            await event_bus.set_state(AssistantState.IDLE, reason=decision.reason)
            return

        await event_bus.set_state(AssistantState.SPEAKING, reason=decision.reason)
        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.stream.start",
                payload={
                    "conversation_id": decision.conversation_id,
                    "provider": decision.provider or "ai",
                    "model": decision.model or "",
                    "fallback_used": False,
                },
            ),
        )
        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.stream.delta",
                payload={
                    "conversation_id": decision.conversation_id,
                    "delta": decision.reply_text,
                },
            ),
        )
        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.stream.end",
                payload={
                    "conversation_id": decision.conversation_id,
                    "role": "assistant",
                    "content": decision.reply_text,
                    "provider": decision.provider or "ai",
                    "model": decision.model or "",
                    "speak": True,
                    "ambient_reason": decision.reason,
                    "mood": infer_face_mood(
                        f"{decision.cleaned_text} {decision.reply_text}",
                        get_system_snapshot(),
                    ),
                },
            ),
        )
    except AIProviderError as exc:
        logger.warning("Erro do provider IA na escuta ambiente: %s", exc.message)
        await event_bus.set_state(AssistantState.ERROR, reason="ai_provider_unavailable")
        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.error",
                payload={"message": exc.message},
            ),
        )
    finally:
        _close_ws_session(db, gen)


async def _handle_ws_greet(app: FastAPI, websocket: WebSocket) -> None:
    """Stream a spontaneous, intelligent greeting from the AI brain."""
    db, gen = _open_ws_session(app)
    try:
        await event_bus.set_state(AssistantState.PROCESSING, reason="ai_greeting")
        snapshot = get_system_snapshot()
        recent_convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(3).all()
        recent_titles = [c.title for c in recent_convs if c.title]

        greeting_messages = [
            ChatMessage(role="system", content=build_jarvis_system_prompt(snapshot)),
            ChatMessage(
                role="user",
                content=build_dynamic_greeting_prompt(snapshot, recent_titles),
            ),
        ]

        accumulated: list[str] = []
        used_provider = "jarvis-brain"
        used_model = "fallback"
        stream_started = False

        try:
            async for chunk in ai_manager.stream_chat(db=db, messages=greeting_messages):
                if not stream_started:
                    stream_started = True
                    used_provider = chunk.provider
                    used_model = chunk.model
                    await event_bus.set_state(AssistantState.SPEAKING, reason="ai_greeting")
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type="chat.stream.start",
                            payload={
                                "provider": used_provider,
                                "model": used_model,
                                "fallback_used": chunk.fallback_used,
                            },
                        ),
                    )
                accumulated.append(chunk.delta)
                await event_bus.send_to(
                    websocket,
                    JarvisEvent(
                        type="chat.stream.delta",
                        payload={"delta": chunk.delta},
                    ),
                )
            greeting_text = "".join(accumulated).strip()
            if not greeting_text:
                greeting_text = fallback_dynamic_greeting(snapshot)
            else:
                remember_greeting(greeting_text)
        except AIProviderError:
            greeting_text = fallback_dynamic_greeting(snapshot)
            await event_bus.set_state(AssistantState.SPEAKING, reason="ai_greeting")

        await event_bus.send_to(
            websocket,
            JarvisEvent(
                type="chat.stream.end",
                payload={
                    "role": "assistant",
                    "content": greeting_text,
                    "provider": used_provider,
                    "model": used_model,
                    "speak": True,
                    "mood": infer_face_mood(greeting_text, snapshot),
                },
            ),
        )
    finally:
        _close_ws_session(db, gen)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize logging, database schema, and background telemetry broadcaster."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)
    init_db()
    logger.info("J.A.R.V.I.S. Backend inicializado (env=%s)", settings.app_env)
    telemetry_task = asyncio.create_task(_telemetry_broadcaster())
    if (
        settings.voice_native_autostart
        and "PYTEST_CURRENT_TEST" not in os.environ
        and native_voice_service.is_supported()
    ):
        await native_voice_service.start()
    try:
        yield
    finally:
        await native_voice_service.stop()
        telemetry_task.cancel()
        try:
            await telemetry_task
        except asyncio.CancelledError:
            pass
        logger.info("J.A.R.V.I.S. Backend encerrado.")


def create_app() -> FastAPI:
    """Application factory creating the configured FastAPI instance."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Just A Rather Very Intelligent System — Backend API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    frontend_index = frontend_dist / "index.html"
    frontend_assets = frontend_dist / "assets"
    if frontend_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="frontend-assets")

    @app.get("/")
    async def root(request: Request):
        """Serve desktop SPA to browser requests or JSON identification to API clients."""
        accept = request.headers.get("accept", "")
        if "text/html" in accept and frontend_index.is_file():
            return FileResponse(frontend_index)
        return JSONResponse(
            {
                "service": settings.app_name,
                "status": "operational",
                "docs": "/docs",
                "health": "/api/v1/health",
            }
        )

    @app.get("/app")
    async def desktop_app():
        """Dedicated Phase 10 desktop entry point serving the compiled SPA."""
        if frontend_index.is_file():
            return FileResponse(frontend_index)
        return JSONResponse(
            {
                "service": settings.app_name,
                "status": "frontend_dist_missing",
                "hint": "Executa 'cd frontend && npm run build' para gerar frontend/dist.",
            },
            status_code=503,
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Real-time bidirectional WebSocket channel for state, telemetry, and AI streaming."""
        await event_bus.connect(websocket)
        active_chat_task: asyncio.Task[None] | None = None

        async def _cancel_active_chat() -> None:
            nonlocal active_chat_task
            if active_chat_task is not None and not active_chat_task.done():
                active_chat_task.cancel()
                try:
                    await active_chat_task
                except asyncio.CancelledError:
                    pass
            active_chat_task = None

        try:
            while True:
                data: Dict[str, Any] = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(type="pong", payload={"state": event_bus.state.value}),
                    )
                elif msg_type == "system.request":
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type=EventType.SYSTEM_UPDATED.value,
                            payload=get_system_snapshot(),
                        ),
                    )
                elif msg_type == "assistant.set_state":
                    requested = data.get("state", "idle")
                    try:
                        new_state = AssistantState(requested)
                        await event_bus.set_state(new_state, reason="client_request")
                    except ValueError:
                        await event_bus.send_to(
                            websocket,
                            JarvisEvent(
                                type=EventType.ASSISTANT_ERROR.value,
                                payload={"message": f"Estado inválido: {requested}"},
                            ),
                        )
                elif msg_type == "chat.send":
                    user_text = str(data.get("content", "")).strip()
                    if user_text:
                        await _cancel_active_chat()
                        raw_conv_id = data.get("conversation_id")
                        conv_id = int(raw_conv_id) if raw_conv_id is not None else None
                        provider = data.get("provider")
                        model = data.get("model")
                        active_chat_task = asyncio.create_task(
                            _handle_ws_chat(
                                app=app,
                                websocket=websocket,
                                user_text=user_text,
                                conversation_id=conv_id,
                                provider_override=str(provider) if provider else None,
                                model_override=str(model) if model else None,
                            )
                        )
                elif msg_type == "voice.ambient_utterance":
                    user_text = str(data.get("content", "")).strip()
                    if user_text:
                        await _cancel_active_chat()
                        raw_conv_id = data.get("conversation_id")
                        conv_id = int(raw_conv_id) if raw_conv_id is not None else None
                        active_chat_task = asyncio.create_task(
                            _handle_ws_ambient(
                                app=app,
                                websocket=websocket,
                                user_text=user_text,
                                conversation_id=conv_id,
                            )
                        )
                elif msg_type == "assistant.greet":
                    await _cancel_active_chat()
                    active_chat_task = asyncio.create_task(
                        _handle_ws_greet(app=app, websocket=websocket)
                    )
                elif msg_type == "assistant.interrupt":
                    await _cancel_active_chat()
                    await native_voice_service.interrupt_playback()
                    await event_bus.set_state(AssistantState.IDLE, reason="interrupted")
                elif msg_type == "vision.register":
                    vision_service.browser_bridge.set_client_camera(
                        id(websocket), bool(data.get("available"))
                    )
                elif msg_type == "voice.browser_mic":
                    native_voice_service.set_browser_mic(
                        id(websocket), bool(data.get("active"))
                    )
                elif msg_type == "vision.capture_response":
                    req_id = str(data.get("request_id", ""))
                    img_b64 = str(data.get("image_b64", ""))
                    if req_id and img_b64:
                        vision_service.browser_bridge.resolve_capture(req_id, img_b64)
                else:
                    await event_bus.send_to(
                        websocket,
                        JarvisEvent(
                            type="ack",
                            payload={"received_type": msg_type},
                        ),
                    )
        except WebSocketDisconnect:
            vision_service.browser_bridge.set_client_camera(id(websocket), False)
            native_voice_service.set_browser_mic(id(websocket), False)
            await _cancel_active_chat()
            await event_bus.disconnect(websocket)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro no canal WebSocket: %s", exc)
            vision_service.browser_bridge.set_client_camera(id(websocket), False)
            native_voice_service.set_browser_mic(id(websocket), False)
            await _cancel_active_chat()
            await event_bus.disconnect(websocket)

    return app


app = create_app()
