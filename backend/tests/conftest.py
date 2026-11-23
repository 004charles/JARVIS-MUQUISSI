"""Pytest fixtures for isolated backend testing."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.events import AssistantState, event_bus
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_event_bus_state() -> None:
    """Ensure clean assistant state between tests."""
    event_bus._state = AssistantState.IDLE  # noqa: SLF001


@pytest.fixture(autouse=True)
def _isolate_from_local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests run with the safe defaults, whatever the developer's .env enables."""
    from app.core.config import get_settings

    for key, value in {
        "FULL_ACCESS": "false",
        "BRAIN_AUTO_MEMORY": "false",
        "BRAIN_MIND_ENABLED": "false",
        "VOICE_MIC_AUTO_GAIN": "false",
        "VOICE_SOUND_CUES": "false",
        "VOICE_ECHO_CANCEL": "false",
        "AI_ROUTING": "false",
        "VOICE_AI_PROVIDER": "",
        "GROQ_API_KEY": "",
        "GEMINI_API_KEY": "",
    }.items():
        monkeypatch.setenv(key, value)
    settings = get_settings()
    monkeypatch.setattr(settings, "full_access", False)
    monkeypatch.setattr(settings, "brain_auto_memory", False)
    monkeypatch.setattr(settings, "brain_mind_enabled", False)
    # Never write test noise into the real logs/jarvis.log
    import tempfile

    monkeypatch.setattr(settings, "log_dir", Path(tempfile.mkdtemp(prefix="stella-test-logs-")))
    monkeypatch.setattr(settings, "brain_quiet_hours", "")

    from app.brain.state import MindState
    import app.brain.state as state_module

    fresh = MindState()
    monkeypatch.setattr(state_module, "mind_state", fresh)
    import app.brain.mind as mind_module

    monkeypatch.setattr(mind_module, "mind_state", fresh)
    monkeypatch.setattr(settings, "voice_ai_provider", "")
    monkeypatch.setattr(settings, "groq_api_key", "")


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Provide an isolated SQLite database session per test."""
    db_file = tmp_path / "test_jarvis.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient wired to the isolated test database."""
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
