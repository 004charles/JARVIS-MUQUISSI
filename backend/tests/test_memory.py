"""Tests for Phase 7 controlled memory layers, secret filtering, tools, and REST API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.manager import AIManager
from app.core.config import Settings
from app.database.models import Conversation, Message
from app.memory.service import SensitiveMemoryError, memory_service
from app.security.permissions import PermissionLevel, SecurityPolicy
from app.tools.registry import ToolRegistry


def test_memory_crud_search_and_secret_blocking(
    client: TestClient, db_session: Session
) -> None:
    # Reject secrets via service and REST
    with pytest.raises(SensitiveMemoryError):
        memory_service.create_memory(
            db_session,
            category="long_term",
            content="Minha senha: password=SuperSecret123",
        )

    bad_resp = client.post(
        "/api/v1/memory",
        json={"category": "long_term", "content": "Chave gsk_AbCdEfGhIjKlMnOpQrStUvWx"},
    )
    assert bad_resp.status_code == 400
    assert "segurança" in bad_resp.json()["detail"].lower()

    # Create valid project and long-term memories
    c1 = client.post(
        "/api/v1/memory",
        json={
            "category": "project",
            "content": "Projeto Edukangola usa Python, Django e PostgreSQL.",
            "source": "user",
        },
    )
    assert c1.status_code == 201
    mem_id = c1.json()["id"]

    c2 = client.post(
        "/api/v1/memory",
        json={
            "category": "preference",
            "content": "Carlos prefere respostas diretas em Português.",
            "source": "user",
        },
    )
    assert c2.status_code == 201

    # Search by keyword
    search_resp = client.get("/api/v1/memory?q=Edukangola")
    assert search_resp.status_code == 200
    items = search_resp.json()["items"]
    assert len(items) == 1
    assert "Django" in items[0]["content"]

    # Update memory
    upd_resp = client.put(
        f"/api/v1/memory/{mem_id}",
        json={"content": "Projeto Edukangola usa Django 5 e PostgreSQL."},
    )
    assert upd_resp.status_code == 200
    assert "Django 5" in upd_resp.json()["content"]

    # Delete memory
    del_resp = client.delete(f"/api/v1/memory/{mem_id}")
    assert del_resp.status_code == 200
    assert client.get("/api/v1/memory?q=Edukangola").json()["items"] == []


def test_ai_context_injects_relevant_approved_memories(db_session: Session) -> None:
    memory_service.create_memory(
        db_session,
        category="project",
        content="O projeto Edukangola está estruturado em Django.",
        approved=True,
    )
    memory_service.create_memory(
        db_session,
        category="long_term",
        content="Memória pendente não aprovada",
        approved=False,
    )

    conv = Conversation(title="Contexto Memória")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    db_session.add(
        Message(
            conversation_id=conv.id,
            role="user",
            content="Qual stack usa o Edukangola?",
        )
    )
    db_session.commit()

    manager = AIManager(Settings())
    msgs = manager.build_conversation_messages(db_session, conv.id)
    system_prompt = msgs[0].content
    assert "Edukangola" in system_prompt
    assert "Django" in system_prompt
    assert "não aprovada" not in system_prompt


@pytest.mark.asyncio
async def test_save_memory_tool_requires_confirmation_and_blocks_secrets(
    tmp_path: Path, db_session: Session
) -> None:
    policy = SecurityPolicy(
        Settings(allowed_directories=str(tmp_path), require_confirmation_level_2=True)
    )
    registry = ToolRegistry(policy=policy)

    # Secret must be blocked at Level 3 before asking confirmation
    blocked = await registry.invoke(
        db_session,
        "save_memory",
        {"category": "long_term", "content": "API token sk-1234567890abcdef1234"},
    )
    assert blocked.status == "blocked"
    assert blocked.permission_level == PermissionLevel.RESTRICTED

    # Valid memory pauses for Level 2 confirmation
    pending = await registry.invoke(
        db_session,
        "save_memory",
        {"category": "preference", "content": "Carlos prefere dark mode azul ciano."},
    )
    assert pending.status == "awaiting_confirmation"
    assert pending.approval is not None
    assert memory_service.list_memories(db_session) == []

    approved = await registry.approve_pending(db_session, pending.approval.id)
    assert approved.status == "executed"
    stored = memory_service.list_memories(db_session)
    assert len(stored) == 1
    assert "dark mode" in stored[0].content

    search_out = await registry.invoke(
        db_session, "search_memory", {"query": "dark mode"}
    )
    assert search_out.status == "executed"
    assert len(search_out.result.output["matches"]) == 1  # type: ignore[union-attr]
