"""Keep the microphone gain sane: clipped audio ruins speech recognition and beat detection.

Browsers (WebRTC auto-gain) and other apps push the system input volume to 100 %, which on
this laptop saturates the internal mic. The guard sets the PipeWire source volume on start,
lowers it when it hears clipping, and puts it back if another app raises it again.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time

import numpy as np

from app.core.logging import get_logger

logger = get_logger("voice.mic_guard")

CLIP_LEVEL = 0.97
WINDOW_FRAMES = 62  # ~2 s of 32 ms frames
CHECK_EXTERNAL_EVERY = 10.0


class MicGainGuard:
    def __init__(self, target: float = 0.40, enabled: bool = True) -> None:
        self.target = min(max(target, 0.1), 1.0)
        self.enabled = enabled and bool(shutil.which("wpctl"))
        self._frames = 0
        self._clipped = 0
        self._samples = 0
        self._last_external_check = 0.0
        self._busy = False

    async def _wpctl(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "wpctl", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return out.decode("utf-8", errors="replace")

    async def current_volume(self) -> float | None:
        match = re.search(r"Volume:\s*([0-9.]+)", await self._wpctl("get-volume", "@DEFAULT_AUDIO_SOURCE@"))
        return float(match.group(1)) if match else None

    async def apply(self, volume: float) -> None:
        await self._wpctl("set-volume", "@DEFAULT_AUDIO_SOURCE@", f"{volume:.2f}")

    async def start(self) -> None:
        if not self.enabled:
            return
        try:
            await self.apply(self.target)
            logger.info("Ganho do microfone ajustado para %.2f.", self.target)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Não consegui ajustar o microfone: %s", exc)

    def observe(self, samples: np.ndarray) -> None:
        """Feed every captured frame; adjustments run in the background."""
        if not self.enabled:
            return
        self._frames += 1
        self._samples += len(samples)
        self._clipped += int(np.count_nonzero(np.abs(samples) >= CLIP_LEVEL))
        if self._frames < WINDOW_FRAMES or self._busy:
            return
        clip_ratio = self._clipped / max(self._samples, 1)
        self._frames = self._clipped = self._samples = 0
        now = time.monotonic()
        check_external = now - self._last_external_check >= CHECK_EXTERNAL_EVERY
        if clip_ratio > 0.01 or check_external:
            self._busy = True
            asyncio.create_task(self._adjust(clip_ratio, check_external))

    async def _adjust(self, clip_ratio: float, check_external: bool) -> None:
        try:
            if clip_ratio > 0.01:
                current = await self.current_volume() or self.target
                # If someone else raised it, go back to our target first; then step down.
                self.target = max(0.12, min(self.target, current) - 0.05)
                await self.apply(self.target)
                logger.info("Microfone a saturar (%.0f%%): ganho baixado para %.2f.", clip_ratio * 100, self.target)
            elif check_external:
                self._last_external_check = time.monotonic()
                current = await self.current_volume()
                if current is not None and current > self.target + 0.08:
                    await self.apply(self.target)
                    logger.info("Outra app subiu o microfone para %.2f: reposto %.2f.", current, self.target)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("Ajuste do microfone falhou: %s", exc)
        finally:
            self._busy = False
