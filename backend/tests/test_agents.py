"""Tests for Phase 9 specialized agents orchestrator, scope guards, and REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents import agent_orchestrator, infer_agent_type
from app.ai.manager import ai_manager


def test_infer_agent_type_routing() -> None:
    assert infer_agent_type("Analisa o consumo de CPU e RAM do Ubuntu") == "system"
    assert infer_agent_type("Pesquisa na internet sobre FastAPI 2026") == "research"
    assert infer_agent_type("Corrige o bug no código Python e corre os testes") == "coding"
    assert infer_agent_type("Cria uma tarefa na minha agenda") == "automation"


@pytest.mark.asyncio
async def test_agent_orchestrator_runs_multi_step_mission_and_enforces_scope(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Step 1 tries an out-of-scope tool (blocked), Step 2 calls allowed system_status, Step 3 concludes.
    replies = iter(
        [
            ('<tool_call>{"tool": "web_search", "args": {"query": "test"}}</tool_call>', "fake", "m1", False),
            ('<tool_call>{"tool": "system_status", "args": {}}</tool_call>', "fake", "m1", False),
            ("Sistema estável com CPU e memória normais.", "fake", "m1", False),
        ]
    )

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return next(replies)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)

    result = await agent_orchestrator.run_mission(
        db=db_session,
        goal="Verificar saúde do sistema Ubuntu",
        agent_type="system",
        max_steps=4,
    )
    assert result.agent_type == "system"
    assert result.status == "completed"
    assert "Sistema estável" in result.summary
    assert len(result.steps) == 3
    assert result.steps[0]["status"] == "blocked"
    assert result.steps[1]["action"] == "system_status"
    assert result.steps[1]["status"] == "executed"


@pytest.mark.asyncio
async def test_agent_orchestrator_pauses_for_level_2_confirmation(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = iter(
        [
            (
                '<tool_call>{"tool": "create_file", "args": {"path": "docs/agent_test_tmp.txt", "content": "ok"}}</tool_call>',
                "fake",
                "m1",
                False,
            )
        ]
    )

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return next(replies)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)

    result = await agent_orchestrator.run_mission(
        db=db_session,
        goal="Criar ficheiro de notas",
        agent_type="automation",
    )
    assert result.status == "awaiting_confirmation"
    assert len(result.steps) == 1
    assert result.steps[0]["status"] == "awaiting_confirmation"


def test_agents_rest_endpoints_list_run_and_history(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_resp = client.get("/api/v1/agents")
    assert list_resp.status_code == 200
    agents = list_resp.json()["agents"]
    ids = {a["id"] for a in agents}
    assert ids == {"coding", "system", "research", "automation", "project"}

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return ("Investigação de código concluída sem regressões.", "fake", "m1", False)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)

    run_resp = client.post(
        "/api/v1/agents/run",
        json={"agent_type": "coding", "goal": "Rever arquitetura do backend"},
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "completed"
    assert "sem regressões" in run_data["summary"]

    runs_resp = client.get("/api/v1/agents/runs")
    assert runs_resp.status_code == 200
    runs = runs_resp.json()["runs"]
    assert any(r["id"] == run_data["id"] for r in runs)
