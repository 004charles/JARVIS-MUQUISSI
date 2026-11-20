"""Tests for Phase 4 tools, three-tier security policy, Level 2 approvals, and audit logs."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import main as app_main
from app.ai.manager import AIManager
from app.ai.ollama_provider import OllamaProvider
from app.api import tools as tools_api
from app.core.config import Settings
from app.security.audit import list_action_logs
from app.security.permissions import PermissionLevel, SecurityPolicy
from app.tools.registry import ToolRegistry


def _make_registry(tmp_path: Path) -> ToolRegistry:
    settings = Settings(
        allowed_directories=str(tmp_path),
        require_confirmation_level_2=True,
    )
    policy = SecurityPolicy(settings=settings)
    return ToolRegistry(policy=policy)


@pytest.mark.asyncio
async def test_level_1_file_tools_and_security_boundaries(
    tmp_path: Path, db_session: Session
) -> None:
    sample = tmp_path / "hello.txt"
    sample.write_text("Conteúdo autorizado", encoding="utf-8")
    env_secret = tmp_path / ".env"
    env_secret.write_text("API_KEY=segredo", encoding="utf-8")

    registry = _make_registry(tmp_path)

    list_outcome = await registry.invoke(db_session, "list_files", {"directory": str(tmp_path)})
    assert list_outcome.status == "executed"
    names = [e["name"] for e in list_outcome.result.output["entries"]]  # type: ignore[union-attr]
    assert "hello.txt" in names
    assert ".env" not in names

    read_outcome = await registry.invoke(db_session, "read_file", {"path": str(sample)})
    assert read_outcome.status == "executed"
    assert read_outcome.result.output["content"] == "Conteúdo autorizado"  # type: ignore[union-attr]

    # Must block reading .env credential file
    secret_outcome = await registry.invoke(db_session, "read_file", {"path": str(env_secret)})
    assert secret_outcome.status == "failed"
    assert secret_outcome.result is not None
    assert secret_outcome.result.success is False
    assert "sensível" in (secret_outcome.result.error or "").lower()

    # Must block path traversal outside allowed directory
    outside_outcome = await registry.invoke(db_session, "read_file", {"path": "/etc/passwd"})
    assert outside_outcome.result is not None
    assert outside_outcome.result.success is False
    assert "fora dos diretórios autorizados" in (outside_outcome.result.error or "").lower()

    # Must block Level 3 dangerous patterns at registry gate
    sudo_outcome = await registry.invoke(
        db_session, "check_service", {"service": "sudo rm -rf /"}
    )
    assert sudo_outcome.status == "blocked"
    assert sudo_outcome.permission_level == PermissionLevel.RESTRICTED


@pytest.mark.asyncio
async def test_level_2_approval_approve_and_reject_workflow(
    tmp_path: Path, db_session: Session
) -> None:
    registry = _make_registry(tmp_path)
    target_file = tmp_path / "notes" / "plano.txt"

    # First request must pause for Level 2 confirmation and NOT create the file
    pending_outcome = await registry.invoke(
        db_session,
        "create_file",
        {"path": str(target_file), "content": "Plano Fase 4"},
    )
    assert pending_outcome.status == "awaiting_confirmation"
    assert pending_outcome.approval is not None
    assert not target_file.exists()

    # Rejecting must cancel and never write
    rejected = await registry.reject_pending(db_session, pending_outcome.approval.id)
    assert rejected is not None
    assert not target_file.exists()

    # Request again and approve
    pending_2 = await registry.invoke(
        db_session,
        "create_file",
        {"path": str(target_file), "content": "Plano Fase 4"},
    )
    assert pending_2.approval is not None
    approved_outcome = await registry.approve_pending(db_session, pending_2.approval.id)
    assert approved_outcome.status == "executed"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "Plano Fase 4"

    logs = list_action_logs(db_session, limit=10)
    statuses = [row.status for row in logs]
    assert "rejected" in statuses
    assert "executed" in statuses


def test_tools_rest_endpoints_approvals_and_logs(
    client: TestClient, tmp_path: Path
) -> None:
    registry = _make_registry(tmp_path)
    client.app.dependency_overrides[tools_api.get_tool_registry] = lambda: registry

    list_resp = client.get("/api/v1/tools")
    assert list_resp.status_code == 200
    tool_names = [t["name"] for t in list_resp.json()["tools"]]
    assert "system_status" in tool_names
    assert "create_file" in tool_names

    target = tmp_path / "script_note.md"
    exec_resp = client.post(
        "/api/v1/tools/create_file/execute",
        json={"params": {"path": str(target), "content": "# J.A.R.V.I.S."}},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["status"] == "awaiting_confirmation"
    approval_id = exec_data["approval_id"]
    assert not target.exists()

    pending_resp = client.get("/api/v1/tools/approvals")
    assert pending_resp.status_code == 200
    assert len(pending_resp.json()) == 1

    approve_resp = client.post(f"/api/v1/tools/approvals/{approval_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "executed"
    assert target.read_text(encoding="utf-8") == "# J.A.R.V.I.S."

    logs_resp = client.get("/api/v1/tools/logs")
    assert logs_resp.status_code == 200
    assert len(logs_resp.json()) >= 2


def test_websocket_ai_tool_call_orchestration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = _make_registry(tmp_path)
    monkeypatch.setattr(app_main, "tool_registry", registry)

    call_count = 0

    def tool_then_reply_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            lines = (
                json.dumps(
                    {
                        "message": {
                            "content": '<tool_call>{"tool": "system_status", "args": {}}</tool_call>'
                        },
                        "done": True,
                    }
                )
                + "\n"
            )
        else:
            lines = (
                json.dumps(
                    {
                        "message": {"content": "Sistema verificado via ferramenta real."},
                        "done": True,
                    }
                )
                + "\n"
            )
        return httpx.Response(200, content=lines.encode("utf-8"))

    test_manager = AIManager(Settings(ai_default_provider="ollama"))
    test_manager.providers["ollama"] = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5-coder:7b",
        client_factory=lambda timeout: httpx.AsyncClient(
            transport=httpx.MockTransport(tool_then_reply_handler),
            timeout=timeout,
        ),
    )
    monkeypatch.setattr(app_main, "ai_manager", test_manager)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # connection.ready
        websocket.send_json({"type": "chat.send", "content": "Verifica o estado real do sistema"})

        seen_types = []
        end_payload = None
        for _ in range(12):
            ev = websocket.receive_json()
            seen_types.append(ev["type"])
            if ev["type"] == "chat.stream.end":
                end_payload = ev["payload"]
                break

        assert "assistant.executing" in seen_types
        assert "tool.started" in seen_types
        assert "tool.completed" in seen_types
        assert end_payload is not None
        assert end_payload["content"] == "Sistema verificado via ferramenta real."
