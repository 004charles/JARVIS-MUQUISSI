"""Voice synthesis contracts and exceptions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class VoiceError(Exception):
    """Structured error raised by STT/TTS engines."""

    def __init__(self, engine: str, message: str) -> None:
        super().__init__(message)
        self.engine = engine
        self.message = message


@dataclass(frozen=True)
class TTSResult:
    """Synthesized audio payload returned by a TTS provider."""

    audio_bytes: bytes
    media_type: str
    engine: str
    voice: str


class TTSProvider(ABC):
    """Abstract Text-to-Speech provider."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the TTS provider is configured and ready."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize spoken audio bytes from text."""


class STTProvider(ABC):
    """Abstract Speech-to-Text provider."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the STT provider is configured and ready."""

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "speech.wav",
        content_type: str = "audio/wav",
        language: str = "pt",
    ) -> str:
        """Transcribe spoken audio bytes into text."""
