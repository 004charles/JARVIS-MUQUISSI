"""Unlimited free Portuguese neural TTS via Edge Neural Voices."""

from __future__ import annotations

import asyncio
import re
import shutil

import edge_tts

from app.voice.base import TTSProvider, TTSResult, VoiceError

_EDGE_VOICE_PROFILES: dict[str, tuple[str, str, str]] = {
    # Arcanjo speaks warmly and serenely; proclaims Scripture with solemn cathedral resonance
    "Arcanjo": ("pt-PT-DuarteNeural", "-4Hz", "-3%"),
    "Arcanjo-Proclama": ("pt-PT-DuarteNeural", "-8Hz", "-6%"),
    "Muquissi-Mulher": ("pt-BR-FranciscaNeural", "-6Hz", "+4%"),
    "Muquissi-Grave": ("pt-PT-DuarteNeural", "-4Hz", "+6%"),
    "Antonio-Grave": ("pt-BR-AntonioNeural", "-20Hz", "-4%"),
    "pt-PT-DuarteNeural": ("pt-PT-DuarteNeural", "-8Hz", "+0%"),
    "pt-PT-RaquelNeural": ("pt-PT-RaquelNeural", "+0Hz", "+0%"),
    "pt-BR-AntonioNeural": ("pt-BR-AntonioNeural", "-6Hz", "+0%"),
    "pt-BR-FabioNeural": ("pt-BR-AntonioNeural", "-12Hz", "+0%"),
}

AVAILABLE_EDGE_VOICES = list(_EDGE_VOICE_PROFILES.keys())

# Voices that get the heavenly treatment: cathedral reverb, a subtle ethereal chorus, warm lows
# "Não temas…" (Dn 10:19) — conversation: warm, serene, barely processed.
SPEAK_FX = (
    "highpass=f=70,equalizer=f=220:t=q:w=1:g=2.5,equalizer=f=3000:t=q:w=1:g=1,"
    "aecho=0.8:0.4:30:0.10,loudnorm=I=-16:TP=-1.5"
)
# "…a voz das suas palavras era como a voz de uma multidão" (Dn 10:6) — proclamation: solemn resonance.
PROCLAIM_FX = (
    "highpass=f=70,equalizer=f=200:t=q:w=1:g=2,aecho=0.8:0.6:45|90:0.18|0.10,"
    "lowpass=f=10000,loudnorm=I=-16:TP=-1.5"
)
VOICE_FX = {"Arcanjo": SPEAK_FX, "Arcanjo-Proclama": PROCLAIM_FX}
ANGELIC_VOICES = set(VOICE_FX)

_QUOTE_RE = re.compile(r"(«[^»]+»|“[^”]+”|⟪[^⟫]+⟫)")  # Scripture quotes and tongues of angels
_REF_RE = re.compile(r"\b([A-ZÀ-Ý][a-zà-ÿ]+) (\d{1,3}):(\d{1,3})(?:\s*[-\u2010-\u2014]\s*(\d{1,3}))?")


def speakable_references(text: str) -> str:
    """'João 3:16-18' → 'João, capítulo 3, versículos 16 a 18' (so the voice never reads '3:16' as an hour)."""

    def repl(m: re.Match[str]) -> str:
        book, chapter, verse, end = m.groups()
        if end:
            return f"{book}, capítulo {chapter}, versículos {verse} a {end}"
        return f"{book}, capítulo {chapter}, versículo {verse}"

    return _REF_RE.sub(repl, text)


def scripture_segments(text: str, voice: str = "Arcanjo") -> list[tuple[str, str]]:
    """Split text so that quoted Scripture («…») is proclaimed and the rest is spoken serenely."""
    if voice != "Arcanjo":
        return [(text, voice)]
    out: list[tuple[str, str]] = []
    for part in _QUOTE_RE.split(text):
        if not part.strip():
            continue
        if _QUOTE_RE.fullmatch(part):
            out.append((part.strip("«»“”⟪⟫").strip(), "Arcanjo-Proclama"))
        else:
            out.append((part.strip(), "Arcanjo"))
    return out or [(text, voice)]


async def apply_angelic_fx(mp3: bytes, fx: str = PROCLAIM_FX) -> bytes:
    """Run the voice through ffmpeg's angelic chain; returns the original audio if unavailable."""
    if not shutil.which("ffmpeg"):
        return mp3
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-f", "mp3", "-i", "pipe:0", "-af", fx,
            "-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(mp3), timeout=15.0)
        return out if proc.returncode == 0 and out else mp3
    except (OSError, asyncio.TimeoutError):
        return mp3


async def concat_mp3(segments: list[bytes]) -> bytes:
    """Join MP3 segments into one stream (ffmpeg concat); falls back to raw byte concatenation."""
    segments = [s for s in segments if s]
    if len(segments) <= 1 or not shutil.which("ffmpeg"):
        return b"".join(segments)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="arcanjo-voz-") as tmp:
        paths = []
        for i, seg in enumerate(segments):
            path = Path(tmp) / f"{i:03d}.mp3"
            path.write_bytes(seg)
            paths.append(str(path))
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-i", "concat:" + "|".join(paths), "-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return out if proc.returncode == 0 and out else b"".join(segments)
        except (OSError, asyncio.TimeoutError):
            return b"".join(segments)


class EdgeNeuralTTSProvider(TTSProvider):
    """Generates natural Portuguese neural speech with zero daily quota limits."""

    name = "edge-neural-tts"

    def __init__(self, default_voice: str = "Muquissi-Grave", angelic_fx: bool = True) -> None:
        self.angelic_fx = angelic_fx
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
        clean_text = speakable_references(text.strip())
        if not clean_text:
            raise VoiceError(self.name, "Texto vazio para síntese de voz.")

        chosen_voice = voice if voice in AVAILABLE_EDGE_VOICES else self.default_voice
        if chosen_voice == "Arcanjo" and _QUOTE_RE.search(clean_text):
            # Mixed text: serene speech + proclaimed Scripture, joined into one track
            parts = [await self.synthesize(seg, v) for seg, v in scripture_segments(clean_text) if seg.strip()]
            return TTSResult(
                audio_bytes=await concat_mp3([r.audio_bytes for r in parts]),
                media_type="audio/mpeg",
                engine=self.name,
                voice="Arcanjo",
            )
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
        if chosen_voice in ANGELIC_VOICES and self.angelic_fx:
            audio_bytes = await apply_angelic_fx(audio_bytes, VOICE_FX[chosen_voice])

        return TTSResult(
            audio_bytes=audio_bytes,
            media_type="audio/mpeg",
            engine=self.name,
            voice=chosen_voice,
        )
