"""AI provider registry, runtime selection, fallback, and context assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Dict, List, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderStatus
from app.ai.ollama_provider import OllamaProvider
from app.ai.openai_compat_provider import OpenAICompatProvider
from app.ai.prompts import build_jarvis_system_prompt
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.models import Message, SettingEntry
from app.memory.service import memory_service
from app.system.telemetry import get_system_snapshot

logger = get_logger("ai.manager")

SETTING_DEFAULT_PROVIDER = "ai.default_provider"
SETTING_FALLBACK_PROVIDER = "ai.fallback_provider"
SETTING_MODEL_PREFIX = "ai.model."


@dataclass(frozen=True)
class StreamChunk:
    """Streamed text delta annotated with the active provider and model."""

    delta: str
    provider: str
    model: str
    fallback_used: bool = False


def _provider_stream(
    provider: AIProvider,
    messages: Sequence[ChatMessage],
    model: str,
    tools: List[dict] | None,
) -> AsyncIterator[str]:
    """Use native function calling when the provider supports it; otherwise text protocol."""
    if tools and getattr(provider, "supports_native_tools", False):
        return provider.stream(messages, model=model, tools=tools)  # type: ignore[call-arg]
    return provider.stream(messages, model=model)


class AIManager:
    """Coordinates provider selection, persistence of AI config, and chat streaming."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.providers: Dict[str, AIProvider] = {
            "ollama": OllamaProvider(
                base_url=self.settings.ollama_base_url,
                default_model=self.settings.ollama_model,
                timeout=self.settings.ollama_timeout,
            ),
            "openai": OpenAICompatProvider(
                name="openai",
                base_url="https://api.openai.com/v1",
                api_key=self.settings.openai_api_key,
                default_model=self.settings.openai_model,
                suggested_models=["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
                timeout=self.settings.ai_timeout,
            ),
            "groq": OpenAICompatProvider(
                name="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=self.settings.groq_api_key,
                default_model=self.settings.groq_model,
                fallback_models=[
                    m.strip() for m in self.settings.groq_fallback_models.split(",") if m.strip()
                ],
                suggested_models=[
                    "openai/gpt-oss-20b",
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.8-27b",
                ],
                timeout=self.settings.ai_timeout,
            ),
            # Google Gemini through its OpenAI-compatible endpoint (free tier, own quota)
            "gemini": OpenAICompatProvider(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                api_key=self.settings.gemini_api_key,
                default_model=self.settings.gemini_chat_model,
                fallback_models=[
                    m.strip() for m in self.settings.gemini_fallback_models.split(",") if m.strip()
                ],
                suggested_models=["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"],
                timeout=self.settings.ai_timeout,
            ),
            "anthropic": AnthropicProvider(
                api_key=self.settings.anthropic_api_key,
                default_model=self.settings.anthropic_model,
                timeout=self.settings.ai_timeout,
            ),
        }

    def _get_setting(self, db: Session, key: str, default: str = "") -> str:
        entry = db.get(SettingEntry, key)
        return entry.value if entry is not None else default

    def _set_setting(self, db: Session, key: str, value: str) -> None:
        entry = db.get(SettingEntry, key)
        if entry is None:
            entry = SettingEntry(key=key, value=value, category="ai")
            db.add(entry)
        else:
            entry.value = value
        db.commit()

    def get_active_config(self, db: Session) -> dict[str, object]:
        """Return currently selected primary provider, fallback provider, and models."""
        primary = self._get_setting(
            db, SETTING_DEFAULT_PROVIDER, self.settings.ai_default_provider
        )
        if primary not in self.providers:
            primary = "ollama"

        fallback = self._get_setting(
            db, SETTING_FALLBACK_PROVIDER, self.settings.ai_fallback_provider
        )
        if fallback and fallback not in self.providers:
            fallback = ""
        if not fallback and primary != "gemini" and self.settings.gemini_api_key.strip():
            fallback = "gemini"  # free second brain when the primary runs out of quota

        models = {
            name: self._get_setting(db, f"{SETTING_MODEL_PREFIX}{name}", provider.default_model)
            for name, provider in self.providers.items()
        }
        return {
            "default_provider": primary,
            "fallback_provider": fallback,
            "models": models,
        }

    def update_config(
        self,
        db: Session,
        default_provider: str | None = None,
        fallback_provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, object]:
        """Persist validated provider/model preferences in SQLite."""
        if default_provider is not None:
            if default_provider not in self.providers:
                raise ValueError(f"Provider inválido: {default_provider}")
            self._set_setting(db, SETTING_DEFAULT_PROVIDER, default_provider)

        if fallback_provider is not None:
            if fallback_provider and fallback_provider not in self.providers:
                raise ValueError(f"Provider alternativo inválido: {fallback_provider}")
            self._set_setting(db, SETTING_FALLBACK_PROVIDER, fallback_provider)

        current = self.get_active_config(db)
        if model is not None and model.strip():
            target_provider = str(current["default_provider"])
            self._set_setting(db, f"{SETTING_MODEL_PREFIX}{target_provider}", model.strip())
            current = self.get_active_config(db)

        return current

    async def list_provider_statuses(self, db: Session) -> List[ProviderStatus]:
        """Inspect status of all registered AI providers."""
        config = self.get_active_config(db)
        active_models = config["models"]
        assert isinstance(active_models, dict)

        statuses: List[ProviderStatus] = []
        for name, provider in self.providers.items():
            st = await provider.status()
            selected_model = str(active_models.get(name, st.default_model))
            statuses.append(
                ProviderStatus(
                    name=st.name,
                    kind=st.kind,
                    available=st.available,
                    configured=st.configured,
                    default_model=selected_model,
                    models=st.models,
                    detail=st.detail,
                )
            )
        return statuses

    def build_conversation_messages(
        self,
        db: Session,
        conversation_id: int,
        include_system: bool = True,
        tools_catalog: str = "",
    ) -> List[ChatMessage]:
        """Assemble system prompt, relevant memories, and recent conversation history."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(self.settings.ai_max_history_messages)
        )
        rows = list(db.scalars(stmt).all())
        rows.reverse()

        result: List[ChatMessage] = []
        if include_system:
            snapshot = get_system_snapshot()
            latest_user_query = next(
                (r.content for r in reversed(rows) if r.role == "user"),
                "",
            )
            relevant = memory_service.build_context_memories(db, query=latest_user_query)
            memories_block = "\n".join(
                f"- [{m.category}] {m.content}" for m in relevant
            )
            result.append(
                ChatMessage(
                    role="system",
                    content=build_jarvis_system_prompt(
                        snapshot,
                        tools_catalog=tools_catalog,
                        memories_block=memories_block,
                    ),
                )
            )

        recent_cut = len(rows) - 2
        for i, row in enumerate(rows):
            if row.role in ("user", "assistant"):
                content = row.content
                if i < recent_cut and len(content) > 700:
                    content = content[:700] + " […]"  # older turns: the gist is enough
                result.append(ChatMessage(role=row.role, content=content))
        return result

    async def generate_chat(
        self,
        db: Session,
        messages: Sequence[ChatMessage],
        provider_override: str | None = None,
        model_override: str | None = None,
        tools: List[dict] | None = None,
    ) -> tuple[str, str, str, bool]:
        """Generate a complete response with optional fallback provider."""
        chunks: List[str] = []
        used_provider = ""
        used_model = ""
        fallback_used = False

        async for item in self.stream_chat(
            db=db,
            messages=messages,
            provider_override=provider_override,
            model_override=model_override,
            tools=tools,
        ):
            chunks.append(item.delta)
            used_provider = item.provider
            used_model = item.model
            fallback_used = item.fallback_used

        return "".join(chunks), used_provider, used_model, fallback_used

    async def stream_chat(
        self,
        db: Session,
        messages: Sequence[ChatMessage],
        provider_override: str | None = None,
        model_override: str | None = None,
        tools: List[dict] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream deltas from primary provider, falling back cleanly if unreachable."""
        config = self.get_active_config(db)
        primary_name = provider_override or str(config["default_provider"])
        if primary_name not in self.providers:
            raise AIProviderError(primary_name, f"Provider desconhecido: {primary_name}")

        fallback_name = str(config["fallback_provider"] or "")
        active_models = config["models"]
        assert isinstance(active_models, dict)

        primary_provider = self.providers[primary_name]
        primary_model = model_override or str(active_models.get(primary_name, primary_provider.default_model))

        emitted_any = False
        try:
            async for delta in _provider_stream(primary_provider, messages, primary_model, tools):
                emitted_any = True
                yield StreamChunk(
                    delta=delta,
                    provider=primary_name,
                    model=primary_model,
                    fallback_used=False,
                )
            return
        except AIProviderError as primary_exc:
            logger.warning(
                "Provider principal '%s' falhou: %s", primary_name, primary_exc.message
            )
            if (
                emitted_any
                or not fallback_name
                or fallback_name == primary_name
                or fallback_name not in self.providers
            ):
                raise

            fallback_provider = self.providers[fallback_name]
            fallback_model = str(
                active_models.get(fallback_name, fallback_provider.default_model)
            )
            try:
                async for delta in _provider_stream(fallback_provider, messages, fallback_model, tools):
                    yield StreamChunk(
                        delta=delta,
                        provider=fallback_name,
                        model=fallback_model,
                        fallback_used=True,
                    )
            except AIProviderError as fallback_exc:
                raise AIProviderError(
                    primary_name,
                    f"Provider principal ({primary_name}) falhou: {primary_exc.message} | "
                    f"Alternativo ({fallback_name}) também falhou: {fallback_exc.message}",
                ) from fallback_exc


ai_manager = AIManager()
