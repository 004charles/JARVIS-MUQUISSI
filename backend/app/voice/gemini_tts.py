"""Gemini native natural Text-to-Speech provider."""

from __future__ import annotations

import base64
import io
import re
import wave
from collections.abc import Callable

import httpx

from app.voice.base import TTSProvider, TTSResult, VoiceError

AVAILABLE_GEMINI_VOICES = [
    "Charon",
    "Fenrir",
    "Orus",
    "Puck",
    "Kore",
    "Aoede",
]

_RATE_RE = re.compile(r"rate=(\d+)")


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Wrap raw 16-bit signed little-endian PCM audio into a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit L16
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


def _parse_sample_rate(mime_type: str) -> int:
    match = _RATE_RE.search(mime_type)
    return int(match.group(1)) if match else 24000


class GeminiTTSProvider(TTSProvider):
    """Generates natural Portuguese speech using Google Gemini TTS models."""

    name = "gemini-tts"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-preview-tts",
        default_voice: str = "Charon",
        timeout: float = 30.0,
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.default_voice = default_voice
        self.timeout = timeout
        self._custom_factory = client_factory
        self._shared_client: httpx.AsyncClient | None = None

    def _get_client(self, timeout: float) -> tuple[httpx.AsyncClient, bool]:
        if self._custom_factory is not None:
            return self._custom_factory(timeout), True
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(timeout=timeout)
        return self._shared_client, False

    def is_available(self) -> bool:
        """Return True when a Gemini API key is configured."""
        return bool(self.api_key)

    async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize natural speech audio as WAV bytes via Gemini API."""
        if not self.api_key:
            raise VoiceError(
                self.name,
                "GEMINI_API_KEY não configurada no ficheiro .env.",
            )

        clean_text = text.strip()
        if not clean_text:
            raise VoiceError(self.name, "Texto vazio para síntese de voz.")

        chosen_voice = voice or self.default_voice
        if chosen_voice not in AVAILABLE_GEMINI_VOICES:
            chosen_voice = self.default_voice

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Lê em português natural, claro, calmo e profissional "
                                f"como um assistente de IA pessoal: {clean_text}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": chosen_voice}
                    }
                },
            },
        }

        client, should_close = self._get_client(self.timeout)
        try:
            response = await client.post(
                url,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise VoiceError(
                    self.name,
                    f"Erro Gemini TTS ({response.status_code}): {response.text}",
                )
            data = response.json()
        except VoiceError:
            raise
        except httpx.TimeoutException as exc:
            raise VoiceError(self.name, "Tempo limite excedido na síntese de voz.") from exc
        except httpx.RequestError as exc:
            raise VoiceError(self.name, f"Falha de rede na síntese de voz: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

        try:
            parts = data["candidates"][0]["content"]["parts"]
            inline = next(p["inlineData"] for p in parts if "inlineData" in p)
            raw_bytes = base64.b64decode(inline["data"])
            mime_type = str(inline.get("mimeType", "audio/L16;codec=pcm;rate=24000"))
        except (KeyError, IndexError, StopIteration, ValueError) as exc:
            raise VoiceError(
                self.name, "Resposta de áudio inválida recebida da API Gemini TTS."
            ) from exc

        if "wav" in mime_type.lower():
            wav_bytes = raw_bytes
        else:
            wav_bytes = pcm_to_wav(raw_bytes, sample_rate=_parse_sample_rate(mime_type))

        return TTSResult(
            audio_bytes=wav_bytes,
            media_type="audio/wav",
            engine=self.name,
            voice=chosen_voice,
        )
