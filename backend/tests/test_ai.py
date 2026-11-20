"""Tests for Phase 3 AI providers, streaming, fallback, and AI endpoints."""

from __future__ import annotations

import json
from typing import List

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIProviderError, ChatMessage
from app.ai.manager import AIManager
from app.ai.ollama_provider import OllamaProvider
from app.ai.openai_compat_provider import OpenAICompatProvider
from app.core.config import Settings
from app.database.models import Conversation, Message


def _mock_client_factory(handler):  # type: ignore[no-untyped-def]
    def _factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return _factory


@pytest.mark.asyncio
async def test_ollama_provider_status_generate_and_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen2.5-coder:7b"}]},
            )
        if request.url.path == "/api/chat":
            body = json.loads(request.content.decode("utf-8"))
            if body.get("stream"):
                lines = (
                    json.dumps({"message": {"content": "Olá, "}, "done": False})
                    + "\n"
                    + json.dumps({"message": {"content": "Carlos."}, "done": True})
                    + "\n"
                )
                return httpx.Response(200, content=lines.encode("utf-8"))
            return httpx.Response(
                200, json={"message": {"content": "Sistema operacional."}}
            )
        return httpx.Response(404)

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(handler),
    )

    st = await provider.status()
    assert st.available is True
    assert st.models == ["qwen2.5-coder:7b"]

    full = await provider.generate([ChatMessage(role="user", content="Estado?")])
    assert full == "Sistema operacional."

    chunks: List[str] = []
    async for delta in provider.stream([ChatMessage(role="user", content="Olá")]):
        chunks.append(delta)
    assert "".join(chunks) == "Olá, Carlos."


@pytest.mark.asyncio
async def test_openai_compat_and_anthropic_streaming() -> None:
    def openai_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        sse = (
            'data: {"choices":[{"delta":{"content":"Resposta "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"OpenAI."}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=sse.encode("utf-8"))

    openai_provider = OpenAICompatProvider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        default_model="gpt-4o-mini",
        suggested_models=["gpt-4o-mini"],
        client_factory=_mock_client_factory(openai_handler),
    )
    chunks = [
        c
        async for c in openai_provider.stream(
            [ChatMessage(role="user", content="Teste")]
        )
    ]
    assert "".join(chunks) == "Resposta OpenAI."

    def anthropic_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "ant-key"
        sse = (
            'data: {"type":"content_block_delta","delta":{"text":"Olá "}}\n\n'
            'data: {"type":"content_block_delta","delta":{"text":"Claude."}}\n\n'
            'data: {"type":"message_stop"}\n\n'
        )
        return httpx.Response(200, content=sse.encode("utf-8"))

    ant_provider = AnthropicProvider(
        api_key="ant-key",
        default_model="claude-3-5-sonnet-latest",
        client_factory=_mock_client_factory(anthropic_handler),
    )
    ant_chunks = [
        c
        async for c in ant_provider.stream(
            [
                ChatMessage(role="system", content="Sê conciso."),
                ChatMessage(role="user", content="Oi"),
            ]
        )
    ]
    assert "".join(ant_chunks) == "Olá Claude."


@pytest.mark.asyncio
async def test_ai_manager_fallback_and_context_persistence(db_session: Session) -> None:
    settings = Settings(
        ai_default_provider="ollama",
        ai_fallback_provider="groq",
        groq_api_key="groq-secret-test",
    )
    manager = AIManager(settings=settings)

    def fail_ollama(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    def ok_groq(_request: httpx.Request) -> httpx.Response:
        sse = 'data: {"choices":[{"delta":{"content":"Via Groq"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, content=sse.encode("utf-8"))

    manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(fail_ollama),
    )
    manager.providers["groq"] = OpenAICompatProvider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="groq-secret-test",
        default_model="llama-3.3-70b-versatile",
        suggested_models=["llama-3.3-70b-versatile"],
        client_factory=_mock_client_factory(ok_groq),
    )

    conv = Conversation(title="Teste Contexto")
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    db_session.add(Message(conversation_id=conv.id, role="user", content="Olá"))
    db_session.commit()

    context = manager.build_conversation_messages(db_session, conv.id)
    assert context[0].role == "system"
    assert context[-1].content == "Olá"

    text, used_provider, _model, fallback_used = await manager.generate_chat(
        db=db_session, messages=context
    )
    assert text == "Via Groq"
    assert used_provider == "groq"
    assert fallback_used is True


@pytest.mark.asyncio
async def test_ai_manager_raises_clear_error_without_fallback(db_session: Session) -> None:
    manager = AIManager(Settings(ai_default_provider="ollama", ai_fallback_provider=""))

    def fail_ollama(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(fail_ollama),
    )

    with pytest.raises(AIProviderError) as exc_info:
        await manager.generate_chat(
            db=db_session,
            messages=[ChatMessage(role="user", content="Olá")],
        )
    assert "Ollama" in exc_info.value.message


def test_ai_rest_endpoints_providers_config_and_chat(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import ai as ai_api

    test_manager = AIManager(Settings(ai_default_provider="ollama", openai_api_key=""))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:7b"}]})
        if request.url.path == "/api/chat":
            lines = (
                json.dumps({"message": {"content": "Olá, Carlos!"}, "done": True})
                + "\n"
            )
            return httpx.Response(200, content=lines.encode("utf-8"))
        return httpx.Response(404)

    test_manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(handler),
    )
    monkeypatch.setattr(ai_api, "ai_manager", test_manager)

    resp = client.get("/api/v1/ai/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_provider"] == "ollama"
    assert len(data["providers"]) == 4

    cfg_resp = client.put(
        "/api/v1/ai/config",
        json={"default_provider": "ollama", "model": "qwen2.5-coder:7b"},
    )
    assert cfg_resp.status_code == 200

    chat_resp = client.post(
        "/api/v1/ai/chat",
        json={"content": "Olá, Jarvis!"},
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["content"] == "Olá, Carlos!"
    assert chat_data["provider"] == "ollama"
    assert chat_data["conversation_id"] >= 1
