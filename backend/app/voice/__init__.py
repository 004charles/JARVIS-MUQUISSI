"""Modular voice STT/TTS, neural VAD, wake-word, and native Linux listener package."""

from app.voice.base import STTProvider, TTSProvider, TTSResult, VoiceError
from app.voice.edge_tts_provider import AVAILABLE_EDGE_VOICES, EdgeNeuralTTSProvider
from app.voice.gemini_tts import AVAILABLE_GEMINI_VOICES, GeminiTTSProvider, pcm_to_wav
from app.voice.groq_stt import GroqSTTProvider
from app.voice.neural_vad import SileroNeuralVAD, neural_vad
from app.voice.wake_word import WakeEvaluation, WakeWordGate

__all__ = [
    "AVAILABLE_EDGE_VOICES",
    "AVAILABLE_GEMINI_VOICES",
    "EdgeNeuralTTSProvider",
    "GeminiTTSProvider",
    "GroqSTTProvider",
    "STTProvider",
    "SileroNeuralVAD",
    "TTSProvider",
    "TTSResult",
    "VoiceError",
    "WakeEvaluation",
    "WakeWordGate",
    "neural_vad",
    "pcm_to_wav",
]
