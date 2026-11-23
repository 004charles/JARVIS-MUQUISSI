"""She hears music, finds the beat, dances — and doesn't answer song lyrics."""

from __future__ import annotations

import numpy as np
import pytest

from app.voice.music_detector import MusicDetector

SR = 16000
_rng = np.random.default_rng(0)


def _room(secs: float) -> np.ndarray:
    return (0.012 * _rng.standard_normal(int(SR * secs))).astype(np.float32)


def _song(bpm: float, secs: float = 14) -> np.ndarray:
    t = np.arange(int(SR * secs)) / SR
    x = 0.06 * np.sin(2 * np.pi * 220 * t) + 0.012 * _rng.standard_normal(len(t))
    beat = 60 / bpm
    for k in range(int(secs / beat)):
        i, n = int(k * beat * SR), int(0.08 * SR)
        env = np.exp(-np.linspace(0, 8, n))
        x[i : i + n] += 0.5 * env * np.sin(2 * np.pi * 60 * np.arange(n) / SR)
    return x.astype(np.float32)


def _talk(secs: float = 14) -> np.ndarray:
    x = _room(secs)
    i = 0
    while i < len(x):
        n = min(int(SR * _rng.uniform(0.3, 1.2)), len(x) - i)
        x[i : i + n] += (0.15 * _rng.standard_normal(n) * np.abs(np.sin(np.linspace(0, 9, n)))).astype(np.float32)
        i += n + int(SR * _rng.uniform(0.3, 0.9))
    return x


def _run(signal: np.ndarray) -> MusicDetector:
    d = MusicDetector()
    for i in range(0, len(signal) - 511, 512):
        d.feed(signal[i : i + 512])
    return d


@pytest.mark.parametrize("bpm", [95, 120, 150])
def test_detects_music_and_its_tempo(bpm: int) -> None:
    d = _run(np.concatenate([_room(5), _song(bpm)]))
    assert d.state.playing is True
    assert abs(d.state.bpm - bpm) <= 6


def test_talk_and_room_noise_are_not_music() -> None:
    assert _run(np.concatenate([_room(5), _talk()])).state.playing is False
    assert _run(_room(15)).state.playing is False


def test_music_stops_after_silence() -> None:
    d = _run(np.concatenate([_room(5), _song(120), _room(8)]))
    assert d.state.playing is False


@pytest.mark.asyncio
async def test_lyrics_are_ignored_while_music_plays_but_name_works(
    db_session, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import AmbientConversationBrain

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return ("Que som bom!", "fake", "m", False)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)
    brain = AmbientConversationBrain(mode="always_reply")
    brain.music_playing = True
    lyric = await brain.evaluate_and_respond(db_session, "Baby, I love you, dança comigo esta noite")
    assert lyric.should_speak is False and lyric.reason == "music_playing"
    called = await brain.evaluate_and_respond(db_session, "Muquissi, gostas desta música?")
    assert called.should_speak is True


def test_music_enters_her_mind_and_prompt() -> None:
    from app.ai.prompts import build_jarvis_system_prompt
    from app.brain import state

    state.mind_state.set_music(True, 124.0)
    assert "a dançar" in build_jarvis_system_prompt()
