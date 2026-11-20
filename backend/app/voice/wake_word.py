"""Wake-word detection and active conversation window management."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

_WAKE_VARIANTS = ("muquissi", "mukuissi", "muquici", "muquice", "mukissi", "moquissi", "muquisi")
_LEADING_GREETINGS = r"(?:(?:oi|ola|ei|hey|ok|fala|alô|alo)\s+)?"
_WAKE_RE = re.compile(
    rf"^\s*{_LEADING_GREETINGS}(?:{'|'.join(_WAKE_VARIANTS)})[\s,.:;!?-]*(.*)$",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


@dataclass(frozen=True)
class WakeEvaluation:
    """Result of evaluating transcribed speech against wake-word & active window."""

    accepted: bool
    wake_only: bool
    cleaned_text: str
    window_active: bool


class WakeWordGate:
    """Manages 'Jarvis' wake word + hands-free continuous conversation window."""

    def __init__(self, active_window_seconds: int = 45) -> None:
        self.active_window_seconds = active_window_seconds
        self._active_until: float = 0.0

    @property
    def is_window_active(self) -> bool:
        """Return True while inside an active hands-free conversation window."""
        return time.monotonic() < self._active_until

    def touch_window(self, seconds: int | None = None) -> None:
        """Extend the active conversation window."""
        duration = self.active_window_seconds if seconds is None else max(0, seconds)
        self._active_until = time.monotonic() + duration

    def reset_window(self) -> None:
        """Return immediately to passive wake-word standby."""
        self._active_until = 0.0

    def evaluate(self, transcript: str, require_wake_word: bool = True) -> WakeEvaluation:
        """Determine whether transcript should trigger J.A.R.V.I.S."""
        raw = transcript.strip()
        if not raw:
            return WakeEvaluation(
                accepted=False,
                wake_only=False,
                cleaned_text="",
                window_active=self.is_window_active,
            )

        normalized = _strip_accents(raw)
        match = _WAKE_RE.match(normalized)

        # Also catch wake word anywhere inside short opening phrase
        contains_wake = any(
            re.search(rf"\b{variant}\b", normalized, re.IGNORECASE)
            for variant in _WAKE_VARIANTS
        )

        if match:
            self.touch_window()
            remainder_len = len(match.group(1).strip())
            if remainder_len == 0:
                return WakeEvaluation(
                    accepted=True,
                    wake_only=True,
                    cleaned_text="",
                    window_active=True,
                )
            # Preserve original accented text after stripping leading wake phrase
            orig_match = _WAKE_RE.match(raw)
            cleaned = orig_match.group(1).strip() if orig_match else raw
            return WakeEvaluation(
                accepted=True,
                wake_only=False,
                cleaned_text=cleaned or raw,
                window_active=True,
            )

        if contains_wake:
            self.touch_window()
            return WakeEvaluation(
                accepted=True,
                wake_only=False,
                cleaned_text=raw,
                window_active=True,
            )

        if not require_wake_word or self.is_window_active:
            self.touch_window()
            return WakeEvaluation(
                accepted=True,
                wake_only=False,
                cleaned_text=raw,
                window_active=True,
            )

        return WakeEvaluation(
            accepted=False,
            wake_only=False,
            cleaned_text="",
            window_active=False,
        )
