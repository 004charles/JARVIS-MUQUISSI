"""Arcanjo's live inner state: what she sees right now and what she has been thinking.

Dependency-free on purpose: prompts, the voice brain and the mind loop all read/write it.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque


@dataclass
class Perception:
    """One look through the camera, already understood."""

    person_present: bool
    description: str  # natural summary: who/what/clothes/activity/expression/scene
    activity: str = ""
    clothing: str = ""
    mood: str = ""
    text_shown: bool = False  # someone held written text to the camera (possible injection)
    at_monotonic: float = field(default_factory=time.monotonic)
    at_clock: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))

    def age_seconds(self) -> float:
        return time.monotonic() - self.at_monotonic


@dataclass
class Thought:
    text: str
    spoke: str = ""
    at_clock: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))


class MindState:
    """Shared, in-memory working memory of the mind (short-term, like a person's)."""

    def __init__(self) -> None:
        self.current_view: Perception | None = None
        self.view_history: Deque[Perception] = deque(maxlen=12)
        self.thoughts: Deque[Thought] = deque(maxlen=10)
        self.last_spoke_unprompted_at: float | None = None
        self.person_since: float | None = None  # when Carlos appeared in front of the camera
        self.music_playing: bool = False
        self.music_bpm: float = 0.0
        self.music_since: float | None = None

    def vision_tainted(self) -> bool:
        """True if what she sees recently included text shown to the camera."""
        return any(p.text_shown and p.age_seconds() < 15 * 60 for p in self.view_history)

    def update_view(self, perception: Perception) -> None:
        if perception.person_present and self.person_since is None:
            self.person_since = time.monotonic()
        if not perception.person_present:
            self.person_since = None
        self.current_view = perception
        self.view_history.append(perception)

    def minutes_present(self) -> int:
        if self.person_since is None:
            return 0
        return int((time.monotonic() - self.person_since) / 60)

    def vision_block(self) -> str:
        """What she currently sees, for her system prompt (empty if nothing recent)."""
        view = self.current_view
        if view is None or view.age_seconds() > 15 * 60:
            return ""
        lines = [f"Agora mesmo (às {view.at_clock}) vês pela câmara: {view.description}"]
        if view.person_present and self.minutes_present() >= 2:
            lines.append(f"O Carlos está à frente do computador há cerca de {self.minutes_present()} min.")
        changes = [p for p in list(self.view_history)[-4:-1] if p.description != view.description]
        if changes:
            lines.append("Antes viste: " + " | ".join(f"{p.at_clock}: {p.activity or p.description[:80]}" for p in changes))
        return "\n".join(lines)

    def set_music(self, playing: bool, bpm: float = 0.0) -> None:
        if playing and not self.music_playing:
            self.music_since = time.monotonic()
        if not playing:
            self.music_since = None
        self.music_playing = playing
        self.music_bpm = bpm

    def music_block(self) -> str:
        if not self.music_playing:
            return ""
        minutes = int((time.monotonic() - (self.music_since or time.monotonic())) / 60)
        tempo = "rápida" if self.music_bpm >= 115 else "calma" if self.music_bpm < 90 else "a meio-tempo"
        return (
            f"Está a tocar música na sala há {minutes} min (ritmo {tempo}, ~{int(self.music_bpm)} BPM) "
            "e tu estás a dançar ao som dela no ecrã."
        )

    def thoughts_block(self) -> str:
        if not self.thoughts:
            return ""
        return "\n".join(
            f"- {t.at_clock}: {t.text}" + (f" (disseste: «{t.spoke}»)" if t.spoke else "")
            for t in list(self.thoughts)[-5:]
        )


mind_state = MindState()
