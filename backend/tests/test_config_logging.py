"""Configuration, logging, and permission contract tests."""

from pathlib import Path

from app.core.config import Settings
from app.core.logging import setup_logging
from app.security.permissions import PermissionLevel


def test_settings_parses_lists_and_defaults() -> None:
    settings = Settings(
        cors_origins="http://localhost:5173, http://127.0.0.1:5173",
        allowed_directories="/tmp",
    )
    assert settings.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.allowed_directories_list == [Path("/tmp").resolve()]
    assert settings.ai_default_provider == "ollama"


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    logger = setup_logging(log_level="INFO", log_dir=tmp_path)
    logger.info("Teste de registo Fase 1")
    for handler in logger.handlers:
        handler.flush()
    log_file = tmp_path / "jarvis.log"
    assert log_file.exists()
    assert "Teste de registo Fase 1" in log_file.read_text(encoding="utf-8")


def test_permission_levels_ordering() -> None:
    assert PermissionLevel.SAFE < PermissionLevel.CONFIRMATION_REQUIRED
    assert PermissionLevel.CONFIRMATION_REQUIRED < PermissionLevel.RESTRICTED
