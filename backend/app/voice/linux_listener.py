"""Zero-click Ubuntu PipeWire/ALSA continuous neural voice listener & speaker."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import numpy as np

from app.ai.base import AIProviderError
from app.core.config import Settings, get_settings
from app.core.events import AssistantState, event_bus
from app.core.logging import get_logger
from app.database.session import SessionLocal
from app.system.telemetry import get_system_snapshot
from app.voice.ambient_brain import ambient_brain, infer_face_mood
from app.voice.base import VoiceError
from app.voice.edge_tts_provider import EdgeNeuralTTSProvider
from app.voice.gemini_tts import GeminiTTSProvider, pcm_to_wav
from app.voice.groq_stt import GroqSTTProvider
from app.voice.neural_vad import FRAME_SAMPLES, SAMPLE_RATE, SileroNeuralVAD

logger = get_logger("voice.linux_listener")

FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit mono
PRE_ROLL_FRAMES = 12  # ~384 ms
SILENCE_HANGOVER_FRAMES = 24  # ~768 ms
MIN_SPEECH_FRAMES = 8  # ~256 ms
MAX_UTTERANCE_FRAMES = 420  # ~13.4 s


class NativeUbuntuVoiceService:
    """Hands-free Ubuntu PipeWire voice loop powered by Silero Neural VAD."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.vad = SileroNeuralVAD()
        self.wake_gate = ambient_brain.wake_gate
        self._running = False
        self._signal_detected = False
        self._browser_clients: set[int] = set()
        self._task: asyncio.Task[None] | None = None
        self._capture_proc: asyncio.subprocess.Process | None = None
        self._play_proc: asyncio.subprocess.Process | None = None
        self._speaking_lock = False
        self._last_error: str | None = None

    def set_browser_mic(self, client_id: int, active: bool) -> None:
        """Yield to an active browser microphone client to prevent duplicate capture."""
        if active:
            self._browser_clients.add(client_id)
        else:
            self._browser_clients.discard(client_id)

    @property
    def require_wake_word(self) -> bool:
        return ambient_brain.require_wake_word

    @require_wake_word.setter
    def require_wake_word(self, value: bool) -> None:
        ambient_brain.require_wake_word = value

    @property
    def capture_command(self) -> list[str] | None:
        """Select available Linux audio capture binary in RAW 16kHz s16le mode."""
        if shutil.which("pw-record"):
            return [
                "pw-record",
                "--raw",
                "--rate",
                "16000",
                "--channels",
                "1",
                "--format",
                "s16",
                "-",
            ]
        if shutil.which("arecord"):
            return ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-"]
        return None

    @property
    def playback_binary(self) -> str | None:
        """Select available Linux audio playback binary."""
        return shutil.which("ffplay") or shutil.which("pw-play") or shutil.which("aplay")

    def is_supported(self) -> bool:
        """Return True if Linux audio tools and STT credentials are available."""
        return bool(self.capture_command and self.settings.groq_api_key.strip())

    def status(self) -> dict[str, object]:
        """Return current native listener operational state."""
        return {
            "running": self._running,
            "supported": self.is_supported(),
            "signal_detected": self._signal_detected,
            "neural_vad": self.vad.is_available,
            "listening_mode": ambient_brain.mode,
            "require_wake_word": self.require_wake_word,
            "wake_word": self.settings.voice_wake_word,
            "window_active": self.wake_gate.is_window_active,
            "capture_tool": self.capture_command[0] if self.capture_command else None,
            "playback_tool": self.playback_binary,
            "last_error": self._last_error,
        }

    async def start(self) -> bool:
        """Start background PipeWire capture loop if supported and not already running."""
        if self._running:
            return True
        if not self.is_supported():
            self._last_error = "Captura de áudio ou GROQ_API_KEY indisponível."
            return False

        self._running = True
        self._last_error = None
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Escuta neural nativa Ubuntu iniciada (Silero VAD).")
        await event_bus.emit("voice.native.status", self.status())
        return True

    async def stop(self) -> None:
        """Stop native capture and any active local playback."""
        self._running = False
        await self.interrupt_playback()
        if self._capture_proc is not None and self._capture_proc.returncode is None:
            self._capture_proc.terminate()
            try:
                await asyncio.wait_for(self._capture_proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._capture_proc.kill()
        self._capture_proc = None

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Escuta neural nativa Ubuntu parada.")
        await event_bus.emit("voice.native.status", self.status())

    async def interrupt_playback(self) -> None:
        """Stop native speaker playback immediately."""
        if self._play_proc is not None and self._play_proc.returncode is None:
            self._play_proc.terminate()
            try:
                await asyncio.wait_for(self._play_proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._play_proc.kill()
        self._play_proc = None
        self._speaking_lock = False

    async def _run_loop(self) -> None:
        cmd = self.capture_command
        if not cmd:
            self._running = False
            return

        stt = GroqSTTProvider(
            api_key=self.settings.groq_api_key,
            model=self.settings.groq_stt_model,
        )
        tts = GeminiTTSProvider(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_tts_model,
            default_voice=self.settings.gemini_tts_voice,
        )
        edge_tts_fallback = EdgeNeuralTTSProvider(default_voice="Muquissi-Grave")

        try:
            self._capture_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            assert self._capture_proc.stdout is not None
            self.vad.reset()

            pre_roll: list[bytes] = []
            speech_frames: list[bytes] = []
            in_speech = False
            silence_count = 0

            while self._running:
                raw_frame = await self._capture_proc.stdout.readexactly(FRAME_BYTES)

                if self._browser_clients or self._speaking_lock or event_bus.state in (
                    AssistantState.PROCESSING,
                    AssistantState.SPEAKING,
                    AssistantState.EXECUTING,
                ):
                    pre_roll.clear()
                    speech_frames.clear()
                    in_speech = False
                    silence_count = 0
                    continue

                samples = np.frombuffer(raw_frame, dtype=np.int16).astype(np.float32) / 32768.0
                prob = self.vad.frame_probability(samples)

                if not in_speech:
                    pre_roll.append(raw_frame)
                    if len(pre_roll) > PRE_ROLL_FRAMES:
                        pre_roll.pop(0)

                    if prob >= 0.48:
                        in_speech = True
                        silence_count = 0
                        speech_frames = [*pre_roll, raw_frame]
                        pre_roll.clear()
                        if self.wake_gate.is_window_active or not self.require_wake_word:
                            await event_bus.set_state(
                                AssistantState.LISTENING, reason="neural_vad_speech"
                            )
                else:
                    speech_frames.append(raw_frame)
                    if prob >= 0.38:
                        silence_count = 0
                    else:
                        silence_count += 1

                    if (
                        silence_count >= SILENCE_HANGOVER_FRAMES
                        or len(speech_frames) >= MAX_UTTERANCE_FRAMES
                    ):
                        captured = speech_frames
                        speech_frames = []
                        in_speech = False
                        silence_count = 0

                        if len(captured) >= MIN_SPEECH_FRAMES + PRE_ROLL_FRAMES:
                            self._signal_detected = True
                            pcm_bytes = b"".join(captured)
                            await self._process_utterance(pcm_bytes, stt, tts, edge_tts_fallback)
                        elif event_bus.state == AssistantState.LISTENING:
                            await event_bus.set_state(AssistantState.IDLE, reason="short_noise")

        except asyncio.IncompleteReadError:
            self._last_error = "Captura de áudio Ubuntu terminou inesperadamente."
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro na escuta nativa Ubuntu: %s", exc)
            self._last_error = str(exc)
        finally:
            self._running = False

    async def _process_utterance(
        self,
        pcm_bytes: bytes,
        stt: GroqSTTProvider,
        tts: GeminiTTSProvider,
        edge_tts_fallback: EdgeNeuralTTSProvider,
    ) -> None:
        wav_bytes = pcm_to_wav(pcm_bytes, sample_rate=SAMPLE_RATE, channels=1)
        try:
            transcript = await stt.transcribe(
                audio_bytes=wav_bytes,
                filename="native_speech.wav",
                content_type="audio/wav",
                language=self.settings.voice_language,
            )
        except VoiceError as exc:
            logger.warning("Erro STT na escuta nativa: %s", exc.message)
            return

        logger.info("Transcrição nativa: %r", transcript)
        await self._evaluate_and_speak(transcript, tts, edge_tts_fallback)

    async def _evaluate_and_speak(
        self,
        transcript: str,
        tts: GeminiTTSProvider,
        edge_tts_fallback: EdgeNeuralTTSProvider,
    ) -> None:
        self._speaking_lock = True
        db = SessionLocal()
        try:
            decision = await ambient_brain.evaluate_and_respond(
                db=db,
                transcript=transcript,
                source="native",
            )
            if decision.heard:
                await event_bus.emit(
                    "voice.ambient.heard",
                    {
                        "text": decision.cleaned_text,
                        "spoken": decision.should_speak,
                        "reason": decision.reason,
                        "mode": decision.mode,
                        "recent_heard": ambient_brain.recent_heard(6),
                        "mood": infer_face_mood(
                            f"{decision.cleaned_text} {decision.reply_text}",
                            get_system_snapshot(),
                        ),
                    },
                )

            if not decision.should_speak or not decision.reply_text:
                if event_bus.state == AssistantState.LISTENING:
                    await event_bus.set_state(
                        AssistantState.IDLE, reason=decision.reason or "ambient_listening"
                    )
                return

            await event_bus.emit(
                "voice.native.transcript",
                {
                    "text": transcript,
                    "cleaned": decision.cleaned_text,
                    "window_active": decision.window_active,
                },
            )
            await event_bus.set_state(AssistantState.SPEAKING, reason="native_voice_tts")
            await event_bus.emit(
                "chat.stream.end",
                {
                    "conversation_id": decision.conversation_id,
                    "role": "assistant",
                    "content": decision.reply_text,
                    "provider": decision.provider,
                    "model": decision.model,
                    "spoken_natively": True,
                },
            )

            tts_result = None
            try:
                tts_result = await edge_tts_fallback.synthesize(decision.reply_text)
            except VoiceError:
                if tts.is_available():
                    tts_result = await tts.synthesize(decision.reply_text)

            if tts_result is not None:
                await self._play_audio_natively(
                    tts_result.audio_bytes,
                    suffix=".mp3" if "mpeg" in tts_result.media_type else ".wav",
                )
        except (AIProviderError, VoiceError) as exc:
            logger.warning("Erro no ciclo de voz nativa: %s", exc)
            await event_bus.emit("chat.error", {"message": str(exc)})
        finally:
            db.close()
            self._speaking_lock = False
            if self._running:
                await event_bus.set_state(AssistantState.IDLE, reason="native_voice_done")

    async def _play_audio_natively(self, audio_bytes: bytes, suffix: str = ".mp3") -> None:
        if suffix == ".mp3" and shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
        elif shutil.which("pw-play"):
            cmd = ["pw-play"]
        elif shutil.which("aplay"):
            cmd = ["aplay"]
        else:
            return

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        try:
            self._play_proc = await asyncio.create_subprocess_exec(
                *cmd,
                str(tmp_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._play_proc.wait()
        finally:
            self._play_proc = None
            tmp_path.unlink(missing_ok=True)


native_voice_service = NativeUbuntuVoiceService()
