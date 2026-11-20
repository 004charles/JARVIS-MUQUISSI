"""Conversation persistence endpoints for Phase 1 foundation."""

from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Conversation, Message
from app.database.session import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    """Payload to create a new conversation."""

    title: str = Field(default="Nova Conversa", min_length=1, max_length=200)


class MessageCreate(BaseModel):
    """Payload to append a message to a conversation."""

    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)


class MessageOut(BaseModel):
    """Serialized conversation message."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    """Serialized conversation summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=List[ConversationOut])
def list_conversations(db: Session = Depends(get_db)) -> List[Conversation]:
    """List persisted conversations ordered by most recently updated."""
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> Conversation:
    """Create and persist a new conversation."""
    conversation = Conversation(title=payload.title.strip())
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
def list_messages(
    conversation_id: int, db: Session = Depends(get_db)
) -> List[Message]:
    """Return all messages in a conversation."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa não encontrada."
        )
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    conversation_id: int, payload: MessageCreate, db: Session = Depends(get_db)
) -> Message:
    """Persist a message inside an existing conversation."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversa não encontrada."
        )
    message = Message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
