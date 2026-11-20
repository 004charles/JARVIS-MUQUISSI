"""Groq Whisper Speech-to-Text provider for fast Portuguese transcription."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from app.voice.base import STTProvider, VoiceError


class GroqSTTProvider(STTProvider):
    """Transcribes speech audio via Groq Whisper API."""

    name = "groq-whisper"

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
        timeout: float = 20.0,
        base_url: str = "https://api.groq.com/openai/v1",
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (
            lambda t: httpx.AsyncClient(timeout=t)
        )

    def is_available(self) -> bool:
        """Return True when a Groq API key is configured."""
        return bool(self.api_key)

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "speech.wav",
        content_type: str = "audio/wav",
        language: str = "pt",
    ) -> str:
        """Send captured audio to Groq `/audio/transcriptions` and return text."""
        if not self.api_key:
            raise VoiceError(
                self.name, "GROQ_API_KEY não configurada no ficheiro .env."
            )
        if not audio_bytes:
            raise VoiceError(self.name, "Áudio vazio recebido para transcrição.")

        files = {"file": (filename, audio_bytes, content_type)}
        data = {
            "model": self.model,
            "language": language.split("-")[0],
            "response_format": "verbose_json",
            "temperature": "0",
        }

        try:
            async with self._client_factory(self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=data,
                    files=files,
                )
                if response.status_code >= 400:
                    raise VoiceError(
                        self.name,
                        f"Erro Groq STT ({response.status_code}): {response.text}",
                    )
                payload = response.json()
                segments = payload.get("segments")
                if isinstance(segments, list) and segments:
                    kept: list[str] = []
                    for seg in segments:
                        if not isinstance(seg, dict):
                            continue
                        no_speech = float(seg.get("no_speech_prob", 0.0) or 0.0)
                        avg_logprob = float(seg.get("avg_logprob", 0.0) or 0.0)
                        compression = float(seg.get("compression_ratio", 1.0) or 1.0)
                        if no_speech >= 0.65 or avg_logprob <= -1.15 or compression >= 2.4:
                            continue
                        seg_text = str(seg.get("text", "")).strip()
                        if seg_text:
                            kept.append(seg_text)
                    return " ".join(kept).strip()
                return str(payload.get("text", "")).strip()
        except VoiceError:
            raise
        except httpx.TimeoutException as exc:
            raise VoiceError(self.name, "Tempo limite excedido na transcrição de voz.") from exc
        except httpx.RequestError as exc:
            raise VoiceError(self.name, f"Falha de rede na transcrição de voz: {exc}") from exc
