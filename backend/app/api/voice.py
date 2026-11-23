"""Voice status, configuration, STT transcription, and natural TTS synthesis endpoints."""

from __future__ import annotations

from functools import lru_cache
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.events import event_bus
from app.core.logging import get_logger
from app.database.models import SettingEntry
from app.database.session import get_db
from app.voice.ambient_brain import ListeningMode, ambient_brain
from app.voice.base import VoiceError
from app.voice.edge_tts_provider import AVAILABLE_EDGE_VOICES, EdgeNeuralTTSProvider
from app.voice.gemini_tts import AVAILABLE_GEMINI_VOICES, GeminiTTSProvider
from app.voice.groq_stt import GroqSTTProvider
from app.voice.linux_listener import native_voice_service
from app.voice.neural_vad import neural_vad

logger = get_logger("api.voice")

router = APIRouter(prefix="/voice", tags=["voice"])

SETTING_VOICE_NAME = "voice.name"
MAX_AUDIO_BYTES = 15 * 1024 * 1024
ALL_VOICES = AVAILABLE_EDGE_VOICES + AVAILABLE_GEMINI_VOICES
DEFAULT_UNLIMITED_VOICE = get_settings().voice_tts_voice
_gemini_quota_until: float = 0.0


@lru_cache(maxsize=1)
def _cached_tts_provider(api_key: str, model: str, default_voice: str) -> GeminiTTSProvider:
    return GeminiTTSProvider(api_key=api_key, model=model, default_voice=default_voice)


def get_tts_provider(settings: Settings = Depends(get_settings)) -> GeminiTTSProvider:
    """Build or reuse the configured Gemini TTS provider with warm HTTP keep-alive."""
    return _cached_tts_provider(
        settings.gemini_api_key,
        settings.gemini_tts_model,
        settings.gemini_tts_voice,
    )


def get_edge_tts_provider() -> EdgeNeuralTTSProvider:
    """Build the unlimited Edge Neural TTS provider."""
    return EdgeNeuralTTSProvider(default_voice=DEFAULT_UNLIMITED_VOICE)


def get_stt_provider(settings: Settings = Depends(get_settings)) -> GroqSTTProvider:
    """Build the configured Groq Whisper STT provider."""
    return GroqSTTProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_stt_model,
    )


class SynthesizeRequest(BaseModel):
    """Text-to-speech synthesis request payload."""

    text: str = Field(min_length=1, max_length=2500)
    voice: str | None = Field(default=None, max_length=60)


class VoiceConfigUpdate(BaseModel):
    """Voice preference update payload."""

    voice: str = Field(min_length=1, max_length=60)


class NativeConfigUpdate(BaseModel):
    """Toggle passive wake-word gating vs open listening."""

    require_wake_word: bool


class ListeningModeUpdate(BaseModel):
    """Switch Arcanjo between proactive opinion participation, always_reply, or wake_word."""

    mode: ListeningMode


class AmbientEvaluateRequest(BaseModel):
    """Evaluate a transcribed utterance in the ambient social brain."""

    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="browser", max_length=32)
    conversation_id: int | None = None


def _get_saved_voice(db: Session) -> str:
    entry = db.get(SettingEntry, SETTING_VOICE_NAME)
    if entry and entry.value in ALL_VOICES:
        return entry.value
    return DEFAULT_UNLIMITED_VOICE


@router.get("/status")
async def voice_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    gemini_provider: GeminiTTSProvider = Depends(get_tts_provider),
    edge_provider: EdgeNeuralTTSProvider = Depends(get_edge_tts_provider),
    stt_provider: GroqSTTProvider = Depends(get_stt_provider),
) -> dict[str, object]:
    """Return active TTS and STT engine status and available natural voices."""
    active_voice = _get_saved_voice(db)
    is_gemini_voice = active_voice in AVAILABLE_GEMINI_VOICES
    tts_available = edge_provider.is_available() or gemini_provider.is_available()
    stt_available = stt_provider.is_available()
    native_state = native_voice_service.status()
    return {
        "available": tts_available,
        "engine": gemini_provider.name if is_gemini_voice else edge_provider.name,
        "model": settings.gemini_tts_model if is_gemini_voice else "edge-neural",
        "voice": active_voice,
        "available_voices": ALL_VOICES,
        "language": settings.voice_language,
        "stt_available": stt_available,
        "stt_engine": stt_provider.name if stt_available else "unavailable",
        "neural_vad_available": neural_vad.is_available,
        "native_listening": native_state["running"],
        "native_supported": native_state["supported"],
        "native_signal_detected": native_state.get("signal_detected", False),
        "listening_mode": ambient_brain.mode,
        "require_wake_word": native_state["require_wake_word"],
        "window_active": native_state["window_active"],
        "wake_word": native_state["wake_word"],
        "recent_heard": ambient_brain.recent_heard(6),
    }


@router.get("/native/status")
async def get_native_voice_status() -> dict[str, object]:
    """Return status of Ubuntu native PipeWire + Silero VAD listener."""
    return native_voice_service.status()


@router.post("/native/start")
async def start_native_voice() -> dict[str, object]:
    """Start Ubuntu native zero-click neural voice listener."""
    started = await native_voice_service.start()
    if not started:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=native_voice_service.status().get("last_error")
            or "Escuta nativa indisponível.",
        )
    return native_voice_service.status()


@router.post("/native/stop")
async def stop_native_voice() -> dict[str, object]:
    """Stop Ubuntu native neural voice listener."""
    await native_voice_service.stop()
    return native_voice_service.status()


@router.put("/native/config")
async def update_native_voice_config(payload: NativeConfigUpdate) -> dict[str, object]:
    """Update whether the wake word is required when passive."""
    native_voice_service.require_wake_word = payload.require_wake_word
    state = native_voice_service.status()
    await event_bus.emit("voice.native.status", state)
    return state


@router.put("/mode")
async def update_listening_mode(payload: ListeningModeUpdate) -> dict[str, object]:
    """Switch Arcanjo's listening behavior (proactive, always_reply, wake_word)."""
    ambient_brain.set_mode(payload.mode)
    state = native_voice_service.status()
    await event_bus.emit("voice.native.status", state)
    return {**state, "listening_mode": ambient_brain.mode}


@router.post("/ambient/evaluate")
async def evaluate_ambient_utterance(
    payload: AmbientEvaluateRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Evaluate a browser/device spoken transcript for ambient listening and opinions."""
    decision = await ambient_brain.evaluate_and_respond(
        db=db,
        transcript=payload.text,
        source=payload.source,
        conversation_id=payload.conversation_id,
    )
    return {
        "heard": decision.heard,
        "should_speak": decision.should_speak,
        "reason": decision.reason,
        "cleaned_text": decision.cleaned_text,
        "reply_text": decision.reply_text,
        "provider": decision.provider,
        "model": decision.model,
        "conversation_id": decision.conversation_id,
        "window_active": decision.window_active,
        "mode": decision.mode,
        "recent_heard": ambient_brain.recent_heard(6),
    }


@router.put("/config")
async def update_voice_config(
    payload: VoiceConfigUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Persist preferred TTS voice name in SQLite."""
    global _gemini_quota_until
    if payload.voice not in ALL_VOICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Voz inválida. Opções: {', '.join(ALL_VOICES)}",
        )
    _gemini_quota_until = 0.0
    entry = db.get(SettingEntry, SETTING_VOICE_NAME)
    if entry is None:
        db.add(SettingEntry(key=SETTING_VOICE_NAME, value=payload.voice, category="voice"))
    else:
        entry.value = payload.voice
    db.commit()
    return {"voice": payload.voice, "available_voices": ALL_VOICES}


@router.post("/synthesize")
async def synthesize_speech(
    payload: SynthesizeRequest,
    db: Session = Depends(get_db),
    gemini_provider: GeminiTTSProvider = Depends(get_tts_provider),
    edge_provider: EdgeNeuralTTSProvider = Depends(get_edge_tts_provider),
) -> Response:
    """Synthesize natural Portuguese speech with automatic fallback to unlimited Edge Neural TTS."""
    global _gemini_quota_until
    chosen_voice = payload.voice or _get_saved_voice(db)
    result = None

    gemini_allowed = (
        chosen_voice in AVAILABLE_GEMINI_VOICES
        and gemini_provider.is_available()
        and time.monotonic() >= _gemini_quota_until
    )
    if gemini_allowed:
        try:
            result = await gemini_provider.synthesize(text=payload.text, voice=chosen_voice)
        except VoiceError as exc:
            if "429" in exc.message or "quota" in exc.message.lower():
                _gemini_quota_until = time.monotonic() + 900.0
            logger.warning(
                "Gemini TTS indisponível (%s), a usar voz neural alternativa %s.",
                exc.message[:120],
                DEFAULT_UNLIMITED_VOICE,
            )

    if result is None:
        try:
            edge_voice = (
                chosen_voice
                if chosen_voice in AVAILABLE_EDGE_VOICES
                else DEFAULT_UNLIMITED_VOICE
            )
            result = await edge_provider.synthesize(text=payload.text, voice=edge_voice)
        except VoiceError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=exc.message,
            ) from exc

    return Response(
        content=result.audio_bytes,
        media_type=result.media_type,
        headers={
            "X-Voice-Engine": result.engine,
            "X-Voice-Name": result.voice,
        },
    )


@router.post("/transcribe")
async def transcribe_speech(
    audio: UploadFile = File(...),
    language: str = Form("pt"),
    provider: GroqSTTProvider = Depends(get_stt_provider),
) -> dict[str, object]:
    """Filter noise with Silero Neural VAD, then transcribe speech into text."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ficheiro de áudio vazio.",
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Áudio excede o limite máximo de 15 MB.",
        )

    if neural_vad.is_available:
        has_speech, speech_prob = neural_vad.contains_speech_wav(audio_bytes)
        if not has_speech:
            return {
                "text": "",
                "engine": "silero-vad-filtered",
                "speech_detected": False,
                "speech_probability": speech_prob,
            }

    try:
        text = await provider.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename or "speech.wav",
            content_type=audio.content_type or "audio/wav",
            language=language,
        )
    except VoiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc

    return {"text": text, "engine": provider.name, "speech_detected": True}
