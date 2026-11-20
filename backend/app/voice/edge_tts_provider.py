"""Unlimited free Portuguese neural TTS via Edge Neural Voices."""

from __future__ import annotations

import edge_tts

from app.voice.base import TTSProvider, TTSResult, VoiceError

_EDGE_VOICE_PROFILES: dict[str, tuple[str, str, str]] = {
    "Muquissi-Grave": ("pt-PT-DuarteNeural", "-22Hz", "-5%"),
    "Antonio-Grave": ("pt-BR-AntonioNeural", "-20Hz", "-4%"),
    "pt-PT-DuarteNeural": ("pt-PT-DuarteNeural", "-8Hz", "+0%"),
    "pt-PT-RaquelNeural": ("pt-PT-RaquelNeural", "+0Hz", "+0%"),
    "pt-BR-AntonioNeural": ("pt-BR-AntonioNeural", "-6Hz", "+0%"),
    "pt-BR-FabioNeural": ("pt-BR-AntonioNeural", "-12Hz", "+0%"),
}

AVAILABLE_EDGE_VOICES = list(_EDGE_VOICE_PROFILES.keys())


class EdgeNeuralTTSProvider(TTSProvider):
    """Generates natural Portuguese neural speech with zero daily quota limits."""

    name = "edge-neural-tts"

    def __init__(self, default_voice: str = "Muquissi-Grave") -> None:
        self.default_voice = (
            default_voice
            if default_voice in AVAILABLE_EDGE_VOICES
            else "Muquissi-Grave"
        )

    def is_available(self) -> bool:
        """Edge TTS requires no API key."""
        return True

    async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize natural Portuguese MP3 audio with deep baritone support."""
        clean_text = text.strip()
        if not clean_text:
            raise VoiceError(self.name, "Texto vazio para síntese de voz.")

        chosen_voice = voice if voice in AVAILABLE_EDGE_VOICES else self.default_voice
        backend_voice, pitch, rate = _EDGE_VOICE_PROFILES[chosen_voice]
        chunks: list[bytes] = []
        try:
            communicate = edge_tts.Communicate(
                clean_text,
                backend_voice,
                pitch=pitch,
                rate=rate,
            )
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(chunk["data"])
        except Exception as exc:  # noqa: BLE001
            raise VoiceError(self.name, f"Falha na síntese Edge TTS: {exc}") from exc

        audio_bytes = b"".join(chunks)
        if not audio_bytes:
            raise VoiceError(self.name, "Edge TTS devolveu áudio vazio.")

        return TTSResult(
            audio_bytes=audio_bytes,
            media_type="audio/mpeg",
            engine=self.name,
            voice=chosen_voice,
        )
