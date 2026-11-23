"""WebSocket communication and AI streaming tests."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.ai.manager import AIManager
from app.ai.ollama_provider import OllamaProvider
from app.core.config import Settings


def _mock_client_factory(handler):  # type: ignore[no-untyped-def]
    def _factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return _factory


def test_websocket_connection_ping_and_ai_streaming(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_manager = AIManager(Settings(ai_default_provider="ollama"))

    def ok_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            lines = (
                json.dumps({"message": {"content": "Sistema "}, "done": False})
                + "\n"
                + json.dumps({"message": {"content": "operacional."}, "done": True})
                + "\n"
            )
            return httpx.Response(200, content=lines.encode("utf-8"))
        return httpx.Response(404)

    test_manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(ok_handler),
    )
    monkeypatch.setattr(app_main, "ai_manager", test_manager)

    with client.websocket_connect("/ws") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "connection.ready"
        assert ready["payload"]["state"] == "idle"

        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"

        websocket.send_json({"type": "system.request"})
        sys_event = websocket.receive_json()
        assert sys_event["type"] == "system.updated"
        assert sys_event["payload"]["ram_total_gb"] > 0

        websocket.send_json({"type": "chat.send", "content": "Como está o sistema?"})

        received_types = []
        end_payload = None
        for _ in range(10):
            ev = websocket.receive_json()
            received_types.append(ev["type"])
            if ev["type"] == "chat.stream.end":
                end_payload = ev["payload"]
                break

        assert "assistant.processing" in received_types
        assert "assistant.speaking" in received_types
        assert "chat.stream.start" in received_types
        assert "chat.stream.delta" in received_types
        assert end_payload is not None
        assert end_payload["content"] == "Sistema operacional."
        assert end_payload["provider"] == "ollama"

        # Verify persisted in SQLite
        conv_id = end_payload["conversation_id"]
        msgs_resp = client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.json()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Sistema operacional."

        websocket.send_json({"type": "assistant.interrupt"})
        idle_event = websocket.receive_json()
        assert idle_event["type"] == "assistant.idle"

        websocket.send_json({"type": "assistant.greet"})
        greet_end = None
        for _ in range(6):
            ev = websocket.receive_json()
            if ev["type"] == "chat.stream.end":
                greet_end = ev["payload"]
                break
        assert greet_end is not None
        assert greet_end["content"] == "Sistema operacional."
        assert greet_end["speak"] is True


def test_websocket_reports_clear_error_when_provider_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_manager = AIManager(Settings(ai_default_provider="ollama", ai_fallback_provider=""))

    def fail_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    test_manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=_mock_client_factory(fail_handler),
    )
    monkeypatch.setattr(app_main, "ai_manager", test_manager)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # connection.ready
        websocket.send_json({"type": "chat.send", "content": "Olá"})

        events = [websocket.receive_json() for _ in range(3)]
        types = [e["type"] for e in events]
        assert "assistant.error" in types
        assert "chat.error" in types
        chat_err = next(e for e in events if e["type"] == "chat.error")
        assert "cérebro do Arcanjo" in chat_err["payload"]["message"]  # friendly, no raw provider error
