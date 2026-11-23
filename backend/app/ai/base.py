"""AI provider abstraction contracts and normalized types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import List, Literal, Sequence


@dataclass(frozen=True)
class ChatMessage:
    """Normalized chat message passed to an AI provider."""

    role: str
    content: str


@dataclass(frozen=True)
class ProviderStatus:
    """Operational availability and configuration summary of a provider."""

    name: str
    kind: Literal["local", "external"]
    available: bool
    configured: bool
    default_model: str
    models: List[str] = field(default_factory=list)
    detail: str = ""


class AIProviderError(Exception):
    """Structured error raised when an AI provider cannot fulfill a request."""

    def __init__(self, provider: str, message: str, recoverable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.recoverable = recoverable


def friendly_ai_error(message: str) -> str:
    """Turn raw provider errors into a short message a person can understand."""
    low = message.lower()
    if "413" in low or "429" in low or "503" in low or "high demand" in low or "overloaded" in low or "rate limit" in low or "rate_limit" in low or "quota" in low:
        return (
            "O Céu está muito procurado neste momento (limite do plano gratuito do cérebro de IA). "
            "Tenta de novo daqui a um minuto."
        )
    if "timeout" in low or "network" in low or "rede" in low or "ligar" in low or "connect" in low:
        return "Não consegui contactar o cérebro do Arcanjo. Verifica a ligação à internet e tenta de novo."
    if "api key" in low or "chave" in low or "401" in low:
        return "O cérebro do Arcanjo não está configurado (falta a chave da API)."
    return "O Arcanjo não conseguiu responder agora. Tenta de novo daqui a pouco."


class AIProvider(ABC):
    """Provider-independent interface for local and external LLMs."""

    name: str
    kind: Literal["local", "external"]
    default_model: str

    @abstractmethod
    async def status(self) -> ProviderStatus:
        """Inspect availability, configuration, and selectable models."""

    async def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""
        return (await self.status()).available

    @abstractmethod
    async def generate(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> str:
        """Generate a complete response for the given conversation."""

    @abstractmethod
    def stream(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream response text deltas for the given conversation."""
