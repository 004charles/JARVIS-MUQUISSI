"""AI provider configuration, status inspection, and REST chat endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError
from app.ai.manager import AIManager, ai_manager
from app.database.models import Conversation, Message
from app.database.session import get_db

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_manager() -> AIManager:
    """Dependency returning the active AIManager instance."""
    return ai_manager


class AIConfigUpdate(BaseModel):
    """Payload to update active AI provider, fallback provider, or model."""

    default_provider: str | None = Field(default=None, min_length=1, max_length=40)
    fallback_provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)


class ChatRequest(BaseModel):
    """REST chat payload persisted in SQLite."""

    content: str = Field(min_length=1)
    conversation_id: int | None = None
    provider: str | None = None
    model: str | None = None


@router.get("/providers")
async def list_providers(
    db: Session = Depends(get_db),
    manager: AIManager = Depends(get_ai_manager),
) -> dict[str, object]:
    """Return active AI configuration and availability of every provider."""
    config = manager.get_active_config(db)
    statuses = await manager.list_provider_statuses(db)
    return {
        "default_provider": config["default_provider"],
        "fallback_provider": config["fallback_provider"],
        "providers": [asdict(st) for st in statuses],
    }


@router.put("/config")
async def update_ai_config(
    payload: AIConfigUpdate,
    db: Session = Depends(get_db),
    manager: AIManager = Depends(get_ai_manager),
) -> dict[str, object]:
    """Update active provider, fallback provider, or model selection."""
    try:
        updated = manager.update_config(
            db=db,
            default_provider=payload.default_provider,
            fallback_provider=payload.fallback_provider,
            model=payload.model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    statuses = await manager.list_provider_statuses(db)
    return {
        "default_provider": updated["default_provider"],
        "fallback_provider": updated["fallback_provider"],
        "models": updated["models"],
        "providers": [asdict(st) for st in statuses],
    }


@router.post("/chat")
async def chat_completion(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    manager: AIManager = Depends(get_ai_manager),
) -> dict[str, object]:
    """Send a message to the configured AI provider and persist the turn."""
    if payload.conversation_id is not None:
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversa não encontrada.",
            )
    else:
        title = payload.content.strip()[:60] or "Nova Conversa"
        conversation = Conversation(title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.content.strip(),
    )
    db.add(user_msg)
    db.commit()

    context_messages = manager.build_conversation_messages(db, conversation.id)
    try:
        reply_text, used_provider, used_model, fallback_used = await manager.generate_chat(
            db=db,
            messages=context_messages,
            provider_override=payload.provider,
            model_override=payload.model,
        )
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc

    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=reply_text,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "conversation_id": conversation.id,
        "message_id": assistant_msg.id,
        "role": "assistant",
        "content": reply_text,
        "provider": used_provider,
        "model": used_model,
        "fallback_used": fallback_used,
    }
