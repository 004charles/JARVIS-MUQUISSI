"""Centralized application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application settings backed by `.env` and environment variables."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Arcanjo"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Database
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'jarvis.db').as_posix()}"

    # AI Providers (Phase 3)
    ai_default_provider: str = "ollama"
    ai_fallback_provider: str = ""
    ai_timeout: int = Field(default=60, ge=5, le=600)
    ai_max_history_messages: int = Field(default=16, ge=2, le=100)
    # Escolha do cérebro por pergunta: simples → modelo rápido; profundas → modelo de topo
    ai_routing: bool = True
    # Limites por pessoa (produto público)
    guard_questions_per_minute: int = 8
    guard_questions_per_day: int = 300
    ai_fast_model: str = ""
    ai_deep_model: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout: int = Field(default=60, ge=5, le=600)

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_stt_model: str = "whisper-large-v3-turbo"
    # Cada modelo Groq tem a sua quota por minuto: se um esgotar, passa ao seguinte.
    groq_fallback_models: str = "qwen/qwen3.8-27b,openai/gpt-oss-20b"

    # Security (Phase 4+)
    allowed_directories: str = str(PROJECT_ROOT)
    require_confirmation_level_2: bool = True
    # Acesso total ao computador: terminal, qualquer app/ficheiro. Só ações destrutivas
    # (apagar, sudo, matar processos, desligar...) pedem confirmação.
    full_access: bool = False

    # Cérebro: aprende factos sobre o Carlos e resume conversas automaticamente
    brain_auto_memory: bool = True
    brain_episode_gap_minutes: int = 30
    # Mente: olhos (câmara) + pensamento próprio + iniciativa para falar
    brain_mind_enabled: bool = True
    brain_vision_enabled: bool = True
    brain_vision_interval_seconds: int = 30
    brain_think_interval_seconds: int = 150
    brain_min_initiative_gap_seconds: int = 420
    brain_quiet_hours: str = "23-7"

    # Voice (Fase 6)
    voice_language: str = "pt-PT"
    voice_enabled: bool = False
    voice_native_autostart: bool = True
    voice_wake_word: str = "arcanjo"
    voice_active_window_seconds: int = 60
    # Voz falada (perfis em app/voice/edge_tts_provider.py)
    voice_tts_voice: str = "Arcanjo"
    # Cérebro dedicado à conversa falada (vazio = automático: Groq se houver chave)
    voice_ai_provider: str = ""
    voice_ai_model: str = ""
    # proactive | always_reply | wake_word
    voice_listening_mode: str = "wake_word"
    # Interromper o Arcanjo ao falar por cima (requer auscultadores ou echo-cancel)
    voice_barge_in: bool = False
    # Guarda do microfone: mantém o ganho no ponto certo (o browser/WebRTC costuma pô-lo a 100%
    # e a voz satura). 0.0–1.0 = volume da entrada no PipeWire.
    voice_mic_volume: float = 0.40
    voice_mic_auto_gain: bool = True
    # Cancelamento de eco (PipeWire/WebRTC): o Arcanjo não ouve o que o PC toca nem a própria voz
    voice_echo_cancel: bool = True
    # Com cancelamento de eco ativo, falar por cima interrompe-a
    voice_barge_in_with_aec: bool = True
    # Sons do Arcanjo: "ouvi-te", "a pensar", "vou falar", "erro"
    voice_sound_cues: bool = True
    voice_cue_volume: float = 0.35
    gemini_api_key: str = ""
    # Visão sem Gemini: modelo Groq multimodal (vê imagens da câmara)
    groq_vision_model: str = "qwen/qwen3.8-27b"
    gemini_vision_model: str = "gemini-3.5-flash"
    # Gemini como cérebro de conversa (grátis, quota própria) — reserva automática quando a Groq esgota
    gemini_chat_model: str = "gemini-3.1-flash-lite"
    gemini_fallback_models: str = "gemini-3.5-flash"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_tts_voice: str = "Charon"

    # Logging
    log_dir: Path = PROJECT_ROOT / "logs"

    @field_validator("database_url", mode="before")
    @classmethod
    def _resolve_relative_sqlite_url(cls, value: str) -> str:
        """Resolve relative SQLite URLs against PROJECT_ROOT regardless of cwd."""
        if isinstance(value, str) and value.startswith("sqlite:///./"):
            rel_path = value.removeprefix("sqlite:///./")
            return f"sqlite:///{(PROJECT_ROOT / rel_path).as_posix()}"
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_directories_list(self) -> List[Path]:
        """Parse comma-separated authorized directories as resolved Paths."""
        return [
            Path(p.strip()).expanduser().resolve()
            for p in self.allowed_directories.split(",")
            if p.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
