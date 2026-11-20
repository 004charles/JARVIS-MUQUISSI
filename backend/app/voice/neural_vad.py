"""Lightweight Silero VAD ONNX neural speech detector (no PyTorch required)."""

from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger

logger = get_logger("voice.neural_vad")

DEFAULT_SILERO_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "silero_vad.onnx"
SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
CONTEXT_SAMPLES = 64


class SileroNeuralVAD:
    """Runs Silero VAD recurrent neural network via ONNX Runtime on 16 kHz audio."""

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or DEFAULT_SILERO_MODEL_PATH
        self._session: ort.InferenceSession | None = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)

        if self.model_path.exists():
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            logger.info("Silero VAD neural model carregado: %s", self.model_path.name)

    @property
    def is_available(self) -> bool:
        """Return True if the ONNX neural model is loaded."""
        return self._session is not None

    def reset(self) -> None:
        """Reset recurrent LSTM state and context window."""
        self._state.fill(0.0)
        self._context.fill(0.0)

    def frame_probability(self, samples: np.ndarray) -> float:
        """Compute speech probability (0.0..1.0) for one 512-sample float32 frame."""
        if len(samples) != FRAME_SAMPLES:
            raise ValueError(f"Expected {FRAME_SAMPLES} samples, got {len(samples)}")

        if self._session is None:
            # Deterministic energy fallback only when ONNX model file is absent
            rms = float(np.sqrt(np.mean(np.square(samples))))
            return min(1.0, rms * 18.0)

        frame = samples.astype(np.float32, copy=False).reshape(1, FRAME_SAMPLES)
        model_input = np.concatenate([self._context, frame], axis=1)
        out, new_state = self._session.run(
            None,
            {"input": model_input, "state": self._state, "sr": self._sr},
        )
        self._state = new_state
        self._context = frame[:, -CONTEXT_SAMPLES:]
        return float(out[0][0])

    def contains_speech_wav(
        self,
        wav_bytes: bytes,
        threshold: float = 0.40,
        min_speech_frames: int = 3,
    ) -> tuple[bool, float]:
        """Inspect a 16 kHz mono WAV clip requiring sustained neural speech probability."""
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                rate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
        except wave.Error:
            return True, 1.0

        if sampwidth != 2 or rate != SAMPLE_RATE or not raw:
            return True, 1.0

        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            pcm = pcm[::channels]

        # Reject sub-audible digital silence / low floor hum immediately
        clip_rms = float(np.sqrt(np.mean(np.square(pcm)))) if len(pcm) > 0 else 0.0
        if clip_rms < 0.0025:
            return False, 0.0

        # Use an isolated state for one-shot clip inspection
        saved_state = self._state.copy()
        saved_ctx = self._context.copy()
        self.reset()
        max_prob = 0.0
        speech_frames = 0
        try:
            frame_threshold = max(0.30, threshold - 0.08)
            for idx in range(0, len(pcm) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
                prob = self.frame_probability(pcm[idx : idx + FRAME_SAMPLES])
                if prob > max_prob:
                    max_prob = prob
                if prob >= frame_threshold:
                    speech_frames += 1
                    if speech_frames >= min_speech_frames and max_prob >= threshold:
                        break
        finally:
            self._state = saved_state
            self._context = saved_ctx

        has_speech = max_prob >= threshold and speech_frames >= min_speech_frames
        return has_speech, round(max_prob, 3)


neural_vad = SileroNeuralVAD()
