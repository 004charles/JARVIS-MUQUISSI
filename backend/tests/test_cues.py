"""Stella's sound cues and the cheap 'will I answer this?' pre-check."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from app.voice.cues import SAMPLE_RATE, SoundCues, build_cues


def test_cues_are_short_soft_and_valid_wav(tmp_path: Path) -> None:
    cues = build_cues(volume=0.35)
    assert set(cues) == {"heard", "thinking", "attention", "error"}
    for name, samples in cues.items():
        assert len(samples) / SAMPLE_RATE < 0.5, name  # curtos
        assert float(np.max(np.abs(samples))) < 0.5, name  # suaves, sem saturar
    sc = SoundCues(enabled=True, volume=0.35, directory=tmp_path)
    if sc.enabled:
        sc.prepare()
        with wave.open(str(tmp_path / "heard.wav"), "rb") as wf:
            assert wf.getframerate() == SAMPLE_RATE and wf.getnframes() > 1000


@pytest.mark.parametrize(
    ("mode", "music", "text", "expected"),
    [
        ("always_reply", False, "Que horas são?", True),
        ("always_reply", False, "Obrigado.", False),  # alucinação típica do Whisper
        ("always_reply", True, "dança comigo esta noite baby", False),  # letra de música
        ("always_reply", True, "Stella, que música é esta?", True),
        ("wake_word", False, "Vou buscar um café", False),
        ("wake_word", False, "Estela, abre o Firefox", True),
    ],
)
def test_likely_to_respond(mode: str, music: bool, text: str, expected: bool) -> None:
    from app.voice.ambient_brain import AmbientConversationBrain

    brain = AmbientConversationBrain(mode=mode)  # type: ignore[arg-type]
    brain.music_playing = music
    assert brain.likely_to_respond(text) is expected


@pytest.mark.parametrize(
    ("text", "stray"),
    [("Banacalipsa.", True), ("Música", True), ("Sim.", False), ("Olá!", False),
     ("Stella", False), ("Horas?", False), ("Abre o YouTube", False)],
)
def test_stray_fragments_are_not_answered(text: str, stray: bool) -> None:
    from app.voice.ambient_brain import is_stray_fragment

    assert is_stray_fragment(text) is stray
