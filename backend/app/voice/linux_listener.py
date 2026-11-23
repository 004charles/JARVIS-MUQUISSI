"""Zero-click Ubuntu PipeWire/ALSA continuous neural voice listener & speaker."""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
import tempfile
import time
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
from app.voice.cues import SoundCues
from app.voice.echo_cancel import EchoCanceller
from app.voice.mic_guard import MicGainGuard
from app.voice.music_detector import MusicDetector
from app.voice.neural_vad import FRAME_SAMPLES, SAMPLE_RATE, SileroNeuralVAD

logger = get_logger("voice.linux_listener")

FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit mono
PRE_ROLL_FRAMES = 12  # ~384 ms
SILENCE_HANGOVER_FRAMES = 24  # ~768 ms
MIN_SPEECH_FRAMES = 8  # ~256 ms
MAX_UTTERANCE_FRAMES = 420  # ~13.4 s
BARGE_IN_FRAMES = 12  # ~384 ms of sustained, confident speech over Arcanjo's voice
BARGE_IN_PROB = 0.85
ECHO_TAIL_SECONDS = 0.45  # ignore the mic briefly after playback (room reverb)

_MARKDOWN_RE = re.compile(r"[*_#`>|~]+")
_URL_RE = re.compile(r"https?://\S+")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def clean_for_speech(text: str) -> str:
    """Strip markdown, URLs, emojis and list bullets so TTS sounds like speech."""
    out = _URL_RE.sub("", text)
    out = re.sub(r"^\s*(?:[-•]|\d+[.)])\s+", "", out, flags=re.MULTILINE)
    out = _MARKDOWN_RE.sub("", out)
    out = _EMOJI_RE.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


def split_for_speech(text: str, min_chars: int = 28) -> list[str]:
    """Split into sentence chunks; tiny fragments are merged so prosody stays natural."""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    chunks: list[str] = []
    for part in parts:
        if chunks and len(chunks[-1]) < min_chars:
            chunks[-1] = f"{chunks[-1]} {part}"
        else:
            chunks.append(part)
    return chunks


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
        self._turn_task: asyncio.Task[None] | None = None
        self._interrupted = False
        self._mute_until: float = 0.0
        self._last_voice_at: float = 0.0
        self._recent_max_prob: float = 0.0
        self._recent_prob_reset_at: float = 0.0
        self._utterances = 0
        self._ignored_log_at: float = 0.0
        self.music = MusicDetector()  # music in the room (heard through the clean mic)
        self.pc_music = MusicDetector()  # music the PC itself is playing (sink monitor)
        self._music_sources: dict[str, object] = {}
        self.echo_canceller = EchoCanceller()
        self._capture_target: str | None = None
        self._monitor_proc: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self.cues = SoundCues(
            enabled=self.settings.voice_sound_cues, volume=self.settings.voice_cue_volume
        )
        self.mic_guard = MicGainGuard(
            target=self.settings.voice_mic_volume, enabled=self.settings.voice_mic_auto_gain
        )
        self._tts: GeminiTTSProvider | None = None
        self._edge_tts: EdgeNeuralTTSProvider | None = None
        self._last_error: str | None = None

    def set_browser_mic(self, client_id: int, active: bool) -> None:
        """Yield to an active browser microphone client to prevent duplicate capture."""
        logger.info("Browser %s o microfone (cliente %s).", "assumiu" if active else "largou", client_id)
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
            target = ["--target", self._capture_target] if self._capture_target else []
            return [
                "pw-record",
                *target,
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
            "browser_mic_clients": len(self._browser_clients),
            "max_voice_prob_last_10s": round(self._recent_max_prob, 3),
            "utterances_captured": self._utterances,
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
        if self._monitor_proc is not None and self._monitor_proc.returncode is None:
            self._monitor_proc.terminate()
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
        self._monitor_task = None
        await self.echo_canceller.stop()
        self._capture_target = None

        if self._turn_task is not None and not self._turn_task.done():
            self._turn_task.cancel()
            await asyncio.gather(self._turn_task, return_exceptions=True)
        self._turn_task = None

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
        """Stop native speaker playback immediately (also drops queued sentences)."""
        self._interrupted = True
        if self._play_proc is not None and self._play_proc.returncode is None:
            self._play_proc.terminate()
            try:
                await asyncio.wait_for(self._play_proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._play_proc.kill()
        self._play_proc = None
        self._speaking_lock = False

    @property
    def barge_in_enabled(self) -> bool:
        """Talking over Arcanjo interrupts her. Safe by default once echo cancellation is on
        (her own voice no longer reaches the mic)."""
        return self.settings.voice_barge_in or (
            self._capture_target is not None and self.settings.voice_barge_in_with_aec
        )

    async def _run_loop(self) -> None:
        if self.settings.voice_echo_cancel and shutil.which("pw-record"):
            self._capture_target = await self.echo_canceller.start()
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
        edge_tts_fallback = EdgeNeuralTTSProvider(default_voice=self.settings.voice_tts_voice)
        self._tts, self._edge_tts = tts, edge_tts_fallback

        await self.mic_guard.start()
        self.cues.prepare()
        self._monitor_task = asyncio.create_task(self._pc_music_loop())
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
            barge_count = 0

            while self._running:
                raw_frame = await self._capture_proc.stdout.readexactly(FRAME_BYTES)
                self.mic_guard.observe(
                    np.frombuffer(raw_frame, dtype=np.int16).astype(np.float32) / 32768.0
                )

                # After a barge-in the old turn is winding down: keep capturing the new one.
                busy = not self._interrupted and (
                    self._speaking_lock
                    or event_bus.state
                    in (
                        AssistantState.PROCESSING,
                        AssistantState.SPEAKING,
                        AssistantState.EXECUTING,
                    )
                )
                if self._browser_clients and time.monotonic() - self._ignored_log_at > 30:
                    self._ignored_log_at = time.monotonic()
                    logger.warning(
                        "A ignorar o microfone: a página no browser está a usar o seu próprio "
                        "microfone. Fecha/recarrega a página para o Arcanjo ouvir diretamente."
                    )
                if self._browser_clients or busy or time.monotonic() < self._mute_until:
                    if (
                        busy
                        and self.barge_in_enabled
                        and self._play_proc is not None
                        and not self._browser_clients
                    ):
                        samples = np.frombuffer(raw_frame, dtype=np.int16).astype(np.float32) / 32768.0
                        prob = self.vad.frame_probability(samples)
                        speech_frames.append(raw_frame)
                        if prob >= BARGE_IN_PROB:
                            barge_count += 1
                        else:
                            barge_count = 0
                            speech_frames = speech_frames[-PRE_ROLL_FRAMES:]
                        if barge_count >= BARGE_IN_FRAMES:
                            logger.info("Interrompido pelo Carlos (barge-in).")
                            await self.interrupt_playback()
                            in_speech = True
                            silence_count = 0
                            barge_count = 0
                            pre_roll.clear()
                            await event_bus.set_state(AssistantState.LISTENING, reason="barge_in")
                        continue
                    pre_roll.clear()
                    speech_frames.clear()
                    in_speech = False
                    silence_count = 0
                    barge_count = 0
                    continue

                samples = np.frombuffer(raw_frame, dtype=np.int16).astype(np.float32) / 32768.0
                prob = self.vad.frame_probability(samples)
                if prob >= 0.38:
                    self._last_voice_at = time.monotonic()
                now_m = time.monotonic()
                if now_m - self._recent_prob_reset_at > 10:
                    self._recent_prob_reset_at = now_m
                    self._recent_max_prob = 0.0
                self._recent_max_prob = max(self._recent_max_prob, prob)
                music_change = self.music.feed(samples)
                if music_change is not None:
                    await self._on_music_change(music_change)

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
                            self._utterances += 1
                            logger.info("Ouvi %.1f s de voz — a transcrever…", len(captured) * 0.032)
                            pcm_bytes = b"".join(captured)
                            if self._turn_task is not None and not self._turn_task.done():
                                await asyncio.gather(self._turn_task, return_exceptions=True)
                            # Lock immediately so the reader ignores audio until the turn ends.
                            self._interrupted = False
                            self._speaking_lock = True
                            self._turn_task = asyncio.create_task(
                                self._process_utterance(pcm_bytes, stt, tts, edge_tts_fallback)
                            )
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
            self._speaking_lock = False

    async def _process_utterance(
        self,
        pcm_bytes: bytes,
        stt: GroqSTTProvider,
        tts: GeminiTTSProvider,
        edge_tts_fallback: EdgeNeuralTTSProvider,
    ) -> None:
        self._speaking_lock = True
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
            self._speaking_lock = False
            if event_bus.state == AssistantState.LISTENING:
                await event_bus.set_state(AssistantState.IDLE, reason="stt_error")
            return

        logger.info("Transcrição nativa: %r", transcript)
        if ambient_brain.likely_to_respond(transcript):
            await self.cues.play("heard")
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
            responding = ambient_brain.likely_to_respond(transcript)
            if responding:
                await event_bus.set_state(AssistantState.PROCESSING, reason="thinking")
            async with self.cues.thinking() if responding else contextlib.nullcontext():
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

            await self._speak_pipelined(decision.reply_text, tts, edge_tts_fallback)
        except (AIProviderError, VoiceError) as exc:
            logger.warning("Erro no ciclo de voz nativa: %s", exc)
            await self.cues.play("error")
            from app.ai.base import friendly_ai_error

            await event_bus.emit("chat.error", {"message": friendly_ai_error(str(exc))})
        finally:
            db.close()
            if not self._interrupted:
                self._mute_until = time.monotonic() + ECHO_TAIL_SECONDS
            self._speaking_lock = False
            if self._running and event_bus.state != AssistantState.LISTENING:
                await event_bus.set_state(AssistantState.IDLE, reason="native_voice_done")

    async def _pc_music_loop(self) -> None:
        """Listen to what the PC itself plays (default output monitor) so Arcanjo dances to it,
        even though echo cancellation removes it from the microphone."""
        if not shutil.which("pw-record"):
            return
        try:
            self._monitor_proc = await asyncio.create_subprocess_exec(
                "pw-record", "-P", "{ stream.capture.sink = true }",
                "--raw", "--rate", "16000", "--channels", "1", "--format", "s16", "-",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            assert self._monitor_proc.stdout is not None
            while self._running:
                raw = await self._monitor_proc.stdout.readexactly(FRAME_BYTES)
                if self._speaking_lock:
                    continue  # her own voice is not music
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                change = self.pc_music.feed(samples)
                if change is not None:
                    await self._on_music_change(change, source="pc")
        except (asyncio.IncompleteReadError, OSError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("Monitor de música do PC parou: %s", exc)

    async def _on_music_change(self, state, source: str = "room") -> None:  # type: ignore[no-untyped-def]
        """Music started/stopped/changed tempo: tell her mind and make her face dance.
        Music may come from the room (mic) or from the PC itself (output monitor)."""
        from app.brain.state import mind_state

        self._music_sources[source] = state
        playing_states = [s for s in self._music_sources.values() if getattr(s, "playing", False)]
        if playing_states:
            state = next(
                (s for k, s in self._music_sources.items() if k == "pc" and getattr(s, "playing", False)),
                playing_states[0],
            )
        was_playing = mind_state.music_playing
        mind_state.set_music(state.playing, state.bpm)
        # Lyrics only reach the mic when music plays in the room (PC audio is echo-cancelled).
        room = self._music_sources.get("room")
        room_playing = bool(getattr(room, "playing", False))
        ambient_brain.music_playing = room_playing or (
            state.playing and self._capture_target is None
        )
        await event_bus.emit(
            "music.state",
            {"playing": state.playing, "bpm": state.bpm, "energy": state.energy},
        )
        if state.playing != was_playing:
            logger.info(
                "Música %s%s",
                "a tocar" if state.playing else "parou",
                f" (~{int(state.bpm)} BPM) — a dançar!" if state.playing else "",
            )
            if state.playing:
                from app.brain.mind import mind

                mind.notice()  # she may want to comment on the song

    def can_speak_unprompted(self) -> bool:
        """True when nobody is talking and Arcanjo isn't busy: safe moment to speak up."""
        return (
            self._running
            and self._tts is not None
            and self._edge_tts is not None
            and not self._speaking_lock
            and not self._browser_clients
            and event_bus.state == AssistantState.IDLE
            and time.monotonic() - self._last_voice_at > 4.0
        )

    async def say(self, text: str, conversation_id: int | None = None) -> bool:
        """Speak a sentence on Arcanjo's own initiative. Returns False if it wasn't a good moment."""
        if not text.strip() or not self.can_speak_unprompted():
            return False
        assert self._tts is not None and self._edge_tts is not None
        self._speaking_lock = True
        try:
            await self.cues.play("attention", wait=True)
            await event_bus.set_state(AssistantState.SPEAKING, reason="stella_initiative")
            await event_bus.emit(
                "chat.stream.end",
                {
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": text,
                    "provider": "mind",
                    "model": "initiative",
                    "spoken_natively": True,
                },
            )
            await self._speak_pipelined(text, self._tts, self._edge_tts)
            return True
        except VoiceError as exc:
            logger.warning("Falha ao falar por iniciativa: %s", exc.message)
            return False
        finally:
            if not self._interrupted:
                self._mute_until = time.monotonic() + ECHO_TAIL_SECONDS
            self._speaking_lock = False
            if self._running and event_bus.state != AssistantState.LISTENING:
                await event_bus.set_state(AssistantState.IDLE, reason="initiative_done")

    async def _synthesize_chunk(
        self,
        text: str,
        tts: GeminiTTSProvider,
        edge_tts_fallback: EdgeNeuralTTSProvider,
        voice: str | None = None,
    ):  # type: ignore[no-untyped-def]
        try:
            return await edge_tts_fallback.synthesize(text, voice)
        except VoiceError as exc:
            if tts.is_available():
                return await tts.synthesize(text)
            raise exc

    async def _speak_pipelined(
        self,
        reply_text: str,
        tts: GeminiTTSProvider,
        edge_tts_fallback: EdgeNeuralTTSProvider,
    ) -> None:
        """Start speaking after the first sentence is synthesized; render the next meanwhile."""
        from app.voice.edge_tts_provider import scripture_segments

        # Serene speech vs proclaimed Scripture («…»), decided before sentence splitting
        chunks: list[tuple[str, str | None]] = []
        default_voice = edge_tts_fallback.default_voice
        for segment, voice in scripture_segments(clean_for_speech(reply_text), default_voice):
            chunks.extend((sentence, voice) for sentence in split_for_speech(segment))
        if not chunks:
            return
        self._interrupted = False
        pending = asyncio.create_task(self._synthesize_chunk(chunks[0][0], tts, edge_tts_fallback, chunks[0][1]))
        for index in range(len(chunks)):
            try:
                result = await pending
            except VoiceError as exc:
                logger.warning("Falha TTS numa frase: %s", exc.message)
                result = None
            pending = None
            if index + 1 < len(chunks) and not self._interrupted:
                pending = asyncio.create_task(
                    self._synthesize_chunk(chunks[index + 1][0], tts, edge_tts_fallback, chunks[index + 1][1])
                )
            if self._interrupted:
                break
            if result is not None:
                await self._play_audio_natively(
                    result.audio_bytes,
                    suffix=".mp3" if "mpeg" in result.media_type else ".wav",
                )
            if self._interrupted:
                break
        if pending is not None:
            pending.cancel()

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
