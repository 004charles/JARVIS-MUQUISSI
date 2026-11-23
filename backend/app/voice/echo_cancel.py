"""Acoustic echo cancellation: Arcanjo hears Carlos, not the PC's own speakers.

Without it, anything the laptop plays (a YouTube video, music, Arcanjo's own voice) reaches the
microphone, the voice detector never finds a pause and Whisper gets noise. PipeWire ships a
WebRTC echo canceller; we run it in its own small `pipewire -c` process (no system config is
touched) in *monitor mode*, so it subtracts whatever the default output is playing. It exposes a
clean source node that the listener records from. The process dies with the backend.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger

logger = get_logger("voice.echo_cancel")

SOURCE_NODE = "stella_aec_source"
CONF_PATH = PROJECT_ROOT / "data" / "pipewire" / "stella-echo-cancel.conf"
_CONF = """\
context.properties = { log.level = 1 }
context.spa-libs = {
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}
context.modules = [
    { name = libpipewire-module-rt flags = [ ifexists nofail ] }
    { name = libpipewire-module-protocol-native }
    { name = libpipewire-module-client-node }
    { name = libpipewire-module-adapter }
    { name = libpipewire-module-echo-cancel
      args = {
        library.name = aec/libspa-aec-webrtc
        monitor.mode = true
        audio.rate = 48000
        audio.channels = 1
        audio.position = [ MONO ]
        capture.props = { node.name = "stella.aec.capture" node.passive = true }
        source.props  = { node.name = "%s" node.description = "Arcanjo (sem eco)" }
      }
    }
]
""" % SOURCE_NODE


async def _node_exists(name: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "pw-cli", "ls", "Node", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
    return f'node.name = "{name}"' in out.decode("utf-8", errors="replace")


class EchoCanceller:
    def __init__(self, conf_path: Path = CONF_PATH) -> None:
        self.conf_path = conf_path
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def available(self) -> bool:
        return bool(shutil.which("pipewire") and shutil.which("pw-cli"))

    async def start(self) -> str | None:
        """Start the canceller; returns the clean source node name, or None if unavailable."""
        if not self.available:
            return None
        try:
            if await _node_exists(SOURCE_NODE):
                return SOURCE_NODE  # already running (e.g. backend restarted quickly)
            self.conf_path.parent.mkdir(parents=True, exist_ok=True)
            self.conf_path.write_text(_CONF, encoding="utf-8")
            self._proc = await asyncio.create_subprocess_exec(
                "pipewire", "-c", str(self.conf_path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            for _ in range(25):
                await asyncio.sleep(0.2)
                if self._proc.returncode is not None:
                    break
                if await _node_exists(SOURCE_NODE):
                    logger.info("Cancelamento de eco ativo: o Arcanjo já não ouve o que o PC toca.")
                    return SOURCE_NODE
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Cancelamento de eco indisponível: %s", exc)
        await self.stop()
        logger.warning("Cancelamento de eco não arrancou; a usar o microfone direto.")
        return None

    async def stop(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None
