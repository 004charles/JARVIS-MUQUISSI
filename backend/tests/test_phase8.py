"""Tests for Phase 8 project analysis, automation tools, web safety, and productivity."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import projects as projects_api
from app.automation.web_research import is_safe_public_url, search_web
from app.core.config import Settings
from app.security.permissions import SecurityPolicy


def test_projects_create_and_non_destructive_analyze(
    client: TestClient, tmp_path: Path
) -> None:
    proj_dir = tmp_path / "edukangola"
    proj_dir.mkdir()
    (proj_dir / "manage.py").write_text("#!/usr/bin/env python\n", encoding="utf-8")
    (proj_dir / "requirements.txt").write_text("django>=5.0\n", encoding="utf-8")

    policy = SecurityPolicy(Settings(allowed_directories=str(tmp_path)))
    client.app.dependency_overrides[projects_api.get_security_policy] = lambda: policy

    # Unauthorized directory must be rejected
    bad_resp = client.post(
        "/api/v1/projects",
        json={"name": "Outside", "directory": "/etc"},
    )
    assert bad_resp.status_code == 403

    create_resp = client.post(
        "/api/v1/projects",
        json={"name": "Edukangola", "description": "Plataforma Django", "directory": str(proj_dir)},
    )
    assert create_resp.status_code == 201
    proj_id = create_resp.json()["id"]

    analyze_resp = client.post(f"/api/v1/projects/{proj_id}/analyze")
    assert analyze_resp.status_code == 200
    report = analyze_resp.json()["report"]
    assert "Django" in report["technologies"]
    assert "Python" in report["technologies"]
    assert "django" in report["dependencies"]


def test_tasks_agenda_and_notes_crud(client: TestClient) -> None:
    task_resp = client.post(
        "/api/v1/tasks",
        json={"title": "Rever migrations", "priority": "high"},
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    patch_resp = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "done"

    agenda_resp = client.post(
        "/api/v1/agenda",
        json={"title": "Deploy staging", "start_at": "2026-11-21T10:00:00Z"},
    )
    assert agenda_resp.status_code == 201
    assert len(client.get("/api/v1/agenda").json()) == 1

    note_resp = client.post(
        "/api/v1/notes",
        json={"title": "Arquitetura", "content": "FastAPI + React"},
    )
    assert note_resp.status_code == 201
    assert len(client.get("/api/v1/notes").json()) == 1


@pytest.mark.asyncio
async def test_web_search_parsing_and_ssrf_guard() -> None:
    assert is_safe_public_url("http://127.0.0.1:8000") is False
    assert is_safe_public_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_public_url("file:///etc/passwd") is False

    html_sample = """
    <div class="result">
      <a class="result__a" href="https://fastapi.tiangolo.com/">FastAPI Docs</a>
      <a class="result__snippet">Modern Python web framework.</a>
    </div>
    """

    def mock_ddg(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_sample)

    results = await search_web(
        "FastAPI",
        client_factory=lambda t: httpx.AsyncClient(
            transport=httpx.MockTransport(mock_ddg), timeout=t
        ),
    )
    assert len(results) == 1
    assert results[0]["title"] == "FastAPI Docs"
    assert results[0]["url"] == "https://fastapi.tiangolo.com/"
