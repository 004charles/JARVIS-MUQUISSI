"""Hear music in the room and find its beat (numpy only, runs on the live 32 ms mic frames).

Music vs. talk: music is *continuous* (few pauses) and *rhythmic* (onsets repeat at a steady
period). Speech is bursty with gaps and has no steady beat. We keep ~6 s of per-frame
features — loudness and spectral flux (how much the spectrum jumps = note/drum onsets) —
and every second check continuity + the strength of the onset autocorrelation within the
dance tempo range (70–180 BPM). A few consecutive positive checks switch "music on";
several negative ones switch it off, so short noises don't make her start/stop dancing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque

import numpy as np

FRAME_RATE = 16000 / 512  # 31.25 analysis frames per second
WINDOW_FRAMES = int(FRAME_RATE * 6)  # 6 s of history
EVAL_EVERY_FRAMES = int(FRAME_RATE)  # re-evaluate once per second
MIN_BPM, MAX_BPM = 70.0, 180.0
ON_AFTER, OFF_AFTER = 2, 5  # consecutive evaluations to switch state


@dataclass(frozen=True)
class MusicState:
    playing: bool
    bpm: float = 0.0
    energy: float = 0.0  # 0..1, how intense the music is (dance amplitude)
    confidence: float = 0.0


class MusicDetector:
    def __init__(self) -> None:
        self._rms: Deque[float] = deque(maxlen=WINDOW_FRAMES)
        self._flux: Deque[float] = deque(maxlen=WINDOW_FRAMES)
        self._noise_floor: Deque[float] = deque(maxlen=int(FRAME_RATE * 30))
        self._prev_spectrum: np.ndarray | None = None
        self._frames_since_eval = 0
        self._streak_on = 0
        self._streak_off = 0
        self.state = MusicState(playing=False)
        self._window = np.hanning(512).astype(np.float32)

    def reset(self) -> None:
        self.__init__()

    def feed(self, samples: np.ndarray) -> MusicState | None:
        """Add one 512-sample frame. Returns the new state when it changes (or bpm updates)."""
        rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
        spectrum = np.abs(np.fft.rfft(samples * self._window))
        spectrum = np.log1p(spectrum * 10.0)
        if self._prev_spectrum is None:
            flux = 0.0
        else:
            flux = float(np.sum(np.maximum(spectrum - self._prev_spectrum, 0.0)))
        self._prev_spectrum = spectrum
        self._rms.append(rms)
        self._flux.append(flux)
        if not self.state.playing:
            self._noise_floor.append(rms)  # learn the room's quiet level only without music

        self._frames_since_eval += 1
        if self._frames_since_eval < EVAL_EVERY_FRAMES or len(self._rms) < WINDOW_FRAMES:
            return None
        self._frames_since_eval = 0
        return self._evaluate()

    def analyze(self) -> tuple[bool, float, float, float]:
        """(looks_like_music, bpm, energy, rhythm_strength) for the current window."""
        rms = np.array(self._rms)
        median = float(np.median(rms))
        floor = float(np.percentile(np.array(self._noise_floor), 10)) if self._noise_floor else 0.0
        # Gaps = frames clearly quieter than the sound's own level (and than the room floor,
        # when a quieter room floor is known). Music has almost none; speech has many.
        gate = 0.35 * median
        if floor < 0.5 * median:
            gate = max(gate, floor * 2.0)
        loud = rms > max(gate, 0.003)
        continuity = float(np.mean(loud)) if median > 0.004 else 0.0

        flux = np.array(self._flux)
        flux = flux - np.mean(flux)
        denom = float(np.dot(flux, flux)) + 1e-9

        def corr_at(lag: int) -> float:
            if lag < 1 or lag >= len(flux):
                return 0.0
            return float(np.dot(flux[:-lag], flux[lag:])) / denom

        def pulse(lag: int) -> tuple[float, float]:
            """Beat strength at an integer lag, merging the neighbour the true period falls into
            (frames are 32 ms, so e.g. 120 BPM = 15.6 frames splits between lags 15 and 16).
            Returns (strength, interpolated fractional lag)."""
            centre = corr_at(lag)
            left, right = corr_at(lag - 1), corr_at(lag + 1)
            neighbour, n_lag = (left, lag - 1) if left > right else (right, lag + 1)
            if neighbour <= 0:
                return centre, float(lag)
            total = centre + neighbour
            return total, (lag * centre + n_lag * neighbour) / max(total, 1e-9)

        min_lag = int(FRAME_RATE * 60.0 / MAX_BPM)
        max_lag = int(np.ceil(FRAME_RATE * 60.0 / MIN_BPM))
        candidates = [pulse(lag) for lag in range(min_lag, max_lag + 1)]
        rhythm, lag = max(candidates, key=lambda c: c[0])
        bpm = 60.0 * FRAME_RATE / lag
        # Octave check: a strong pulse at half the period means the real beat is twice as fast.
        half_strength, half_lag = pulse(int(round(lag / 2)))
        if 60.0 * FRAME_RATE / max(half_lag, 1.0) <= MAX_BPM + 10 and half_strength >= 0.75 * rhythm:
            bpm = 60.0 * FRAME_RATE / half_lag
        energy = float(np.clip(np.median(rms) / 0.15, 0.0, 1.0))
        looks_like_music = continuity >= 0.85 and rhythm >= 0.25
        return looks_like_music, bpm, energy, rhythm

    def _evaluate(self) -> MusicState | None:
        looks_like_music, bpm, energy, rhythm = self.analyze()
        if looks_like_music:
            self._streak_on += 1
            self._streak_off = 0
        else:
            self._streak_off += 1
            self._streak_on = 0

        previous = self.state
        if not previous.playing and self._streak_on >= ON_AFTER:
            self.state = MusicState(True, round(bpm, 1), round(energy, 2), round(rhythm, 2))
            return self.state
        if previous.playing and self._streak_off >= OFF_AFTER:
            self.state = MusicState(False)
            return self.state
        if previous.playing and looks_like_music and abs(bpm - previous.bpm) > 4:
            ratio = bpm / max(previous.bpm, 1.0)
            if 0.45 < ratio < 0.55:
                return None  # one-off half-tempo reading: keep dancing at the faster beat
            if 1.8 < ratio < 2.2:
                new_bpm = bpm  # we had locked on half the tempo: jump straight to the real beat
            else:
                new_bpm = previous.bpm * 0.5 + bpm * 0.5  # song changed: glide to the new tempo
            self.state = MusicState(True, round(new_bpm, 1), round(energy, 2), round(rhythm, 2))
            return self.state
        return None
