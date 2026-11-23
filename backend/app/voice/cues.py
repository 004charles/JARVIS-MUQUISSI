"""Arcanjo's sound cues (earcons): heard you → thinking → about to speak → error.

Generated with numpy at startup (no external files) and played with pw-play/aplay. Cues only
play while the listener is already ignoring the microphone, so they never leak into what
Arcanjo transcribes.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import wave
from collections.abc import AsyncGenerator
from pathlib import Path

import numpy as np

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger

logger = get_logger("voice.cues")

SAMPLE_RATE = 44100
SOUNDS_DIR = PROJECT_ROOT / "data" / "sounds"
THINKING_PERIOD = 1.1  # seconds between thinking pulses


def _tone(freqs: list[float], duration: float, volume: float, attack: float = 0.01, release: float = 0.08) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
    wave_sum = sum(np.sin(2 * np.pi * f * t) / (i + 1) for i, f in enumerate(freqs))
    env = np.ones_like(t)
    a, r = int(SAMPLE_RATE * attack), int(SAMPLE_RATE * release)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] *= np.linspace(1, 0, r) ** 2
    return (wave_sum * env * volume).astype(np.float32)


def _silence(duration: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * duration), dtype=np.float32)


def build_cues(volume: float) -> dict[str, np.ndarray]:
    """Soft, short, futuristic tones."""
    v = max(0.0, min(volume, 1.0))
    return {
        # "Ouvi-te": two quick rising notes (E6 → B6)
        "heard": np.concatenate([
            _tone([1318.5, 2637], 0.07, 0.30 * v, release=0.05),
            _silence(0.025),
            _tone([1975.5, 3951], 0.11, 0.26 * v, release=0.09),
        ]),
        # "A pensar": a soft, round pulse (A4 + fifth), slow attack
        "thinking": _tone([440.0, 660.0, 880.0], 0.22, 0.13 * v, attack=0.07, release=0.14),
        # "Vou falar": a warm attention ding (C6 with bell-like overtones)
        "attention": np.concatenate([
            _tone([1046.5, 2093, 3140], 0.09, 0.22 * v, release=0.06),
            _tone([1568.0, 3136, 4704], 0.28, 0.20 * v, release=0.25),
        ]),
        # "Erro": two descending notes
        "error": np.concatenate([
            _tone([523.25, 1046.5], 0.12, 0.25 * v),
            _silence(0.03),
            _tone([392.0, 784.0], 0.2, 0.25 * v, release=0.15),
        ]),
    }


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


class SoundCues:
    def __init__(self, enabled: bool = True, volume: float = 0.35, directory: Path = SOUNDS_DIR) -> None:
        self.player = shutil.which("pw-play") or shutil.which("aplay")
        self.enabled = enabled and self.player is not None
        self.volume = volume
        self.directory = directory
        self._files: dict[str, Path] = {}

    def prepare(self) -> None:
        """(Re)generate the cue files once."""
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        for name, samples in build_cues(self.volume).items():
            path = self.directory / f"{name}.wav"
            write_wav(path, samples)
            self._files[name] = path

    async def play(self, name: str, wait: bool = False) -> None:
        """Play a cue; by default fire-and-forget so it never delays Arcanjo."""
        path = self._files.get(name)
        if not self.enabled or path is None or self.player is None:
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                self.player, str(path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            if wait:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("Som '%s' falhou: %s", name, exc)

    @contextlib.asynccontextmanager
    async def thinking(self) -> AsyncGenerator[None, None]:
        """Soft repeating pulse while Arcanjo thinks; stops the moment the block exits."""
        async def pulse() -> None:
            await asyncio.sleep(0.35)  # quick answers don't need a thinking sound at all
            while True:
                await self.play("thinking")
                await asyncio.sleep(THINKING_PERIOD)

        task = asyncio.create_task(pulse()) if self.enabled else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
