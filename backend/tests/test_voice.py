"""Tests for natural Gemini TTS voice synthesis and endpoints."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import voice as voice_api
from app.voice.base import VoiceError
from app.voice.gemini_tts import GeminiTTSProvider, pcm_to_wav
from app.voice.groq_stt import GroqSTTProvider
from app.voice.neural_vad import SileroNeuralVAD
from app.voice.wake_word import WakeWordGate


def _mock_client_factory(handler):  # type: ignore[no-untyped-def]
    def _factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return _factory


def test_pcm_to_wav_produces_valid_riff_header() -> None:
    wav_data = pcm_to_wav(b"\x00\x00" * 120, sample_rate=24000)
    assert wav_data[:4] == b"RIFF"
    assert wav_data[8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_gemini_tts_provider_synthesizes_wav_and_handles_missing_key() -> None:
    no_key_provider = GeminiTTSProvider(api_key="")
    assert no_key_provider.is_available() is False
    with pytest.raises(VoiceError):
        await no_key_provider.synthesize("Olá")

    fake_pcm = b"\x01\x02" * 200
    encoded_pcm = base64.b64encode(fake_pcm).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "AQ.test-key"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": encoded_pcm,
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    provider = GeminiTTSProvider(
        api_key="AQ.test-key",
        client_factory=_mock_client_factory(handler),
    )
    assert provider.is_available() is True
    result = await provider.synthesize("Olá, Carlos.", voice="Charon")
    assert result.media_type == "audio/wav"
    assert result.voice == "Charon"
    assert result.audio_bytes[:4] == b"RIFF"


def test_voice_endpoints_status_config_and_synthesize(
    client: TestClient,
) -> None:
    fake_pcm = base64.b64encode(b"\x05\x06" * 100).decode("ascii")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": fake_pcm,
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    mock_provider = GeminiTTSProvider(
        api_key="AQ.test-endpoint",
        client_factory=_mock_client_factory(handler),
    )
    client.app.dependency_overrides[voice_api.get_tts_provider] = lambda: mock_provider

    status_resp = client.get("/api/v1/voice/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["available"] is True
    assert "Muquissi-Grave" in status_data["available_voices"]
    assert "pt-PT-DuarteNeural" in status_data["available_voices"]
    assert "Charon" in status_data["available_voices"]

    cfg_resp = client.put("/api/v1/voice/config", json={"voice": "Fenrir"})
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["voice"] == "Fenrir"

    synth_resp = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Sistemas operacionais."},
    )
    assert synth_resp.status_code == 200
    assert synth_resp.headers["content-type"] == "audio/wav"
    assert synth_resp.headers["x-voice-name"] == "Fenrir"
    assert synth_resp.content[:4] == b"RIFF"


def test_voice_synthesize_falls_back_to_edge_when_gemini_quota_exceeded(
    client: TestClient,
) -> None:
    from app.voice.base import TTSResult

    def fail_429(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 429, "message": "quota exceeded"}})

    class FakeEdgeProvider:
        name = "edge-neural-tts"

        def is_available(self) -> bool:
            return True

        async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
            return TTSResult(
                audio_bytes=b"ID3FAKEAUDIO",
                media_type="audio/mpeg",
                engine=self.name,
                voice=voice or "pt-PT-DuarteNeural",
            )

    failing_gemini = GeminiTTSProvider(
        api_key="AQ.test-quota",
        client_factory=_mock_client_factory(fail_429),
    )
    client.app.dependency_overrides[voice_api.get_tts_provider] = lambda: failing_gemini
    client.app.dependency_overrides[voice_api.get_edge_tts_provider] = lambda: FakeEdgeProvider()

    resp = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Teste fallback.", "voice": "Kore"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.headers["x-voice-engine"] == "edge-neural-tts"
    assert resp.headers["x-voice-name"] == "Muquissi-Grave"


def test_voice_transcribe_endpoint_and_stt_provider(client: TestClient) -> None:
    def stt_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer groq-test-key"
        return httpx.Response(200, json={"text": "Olá Jarvis, como está o sistema?"})

    mock_stt = GroqSTTProvider(
        api_key="groq-test-key",
        client_factory=_mock_client_factory(stt_handler),
    )
    client.app.dependency_overrides[voice_api.get_stt_provider] = lambda: mock_stt

    # Non-16kHz audio bypasses 16kHz VAD check cleanly in unit test
    wav_bytes = pcm_to_wav(b"\x01\x02" * 400, sample_rate=8000)
    resp = client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("speech.wav", wav_bytes, "audio/wav")},
        data={"language": "pt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Olá Jarvis, como está o sistema?"
    assert data["engine"] == "groq-whisper"


def test_silero_neural_vad_rejects_silence_and_wake_word_gate() -> None:
    vad = SileroNeuralVAD()
    assert vad.is_available is True

    silence_wav = pcm_to_wav(b"\x00\x00" * 4000, sample_rate=16000)
    has_speech, prob = vad.contains_speech_wav(silence_wav)
    assert has_speech is False
    assert prob < 0.2

    gate = WakeWordGate(active_window_seconds=30)
    assert gate.evaluate("conversa aleatória na sala", require_wake_word=True).accepted is False

    wake_only = gate.evaluate("Muquissi", require_wake_word=True)
    assert wake_only.accepted is True
    assert wake_only.wake_only is True
    assert wake_only.window_active is True

    follow_up = gate.evaluate("como está a memória RAM?", require_wake_word=True)
    assert follow_up.accepted is True
    assert follow_up.cleaned_text == "como está a memória RAM?"

    direct_cmd = gate.evaluate("Ei Muquissi, abre o VS Code", require_wake_word=True)
    assert direct_cmd.accepted is True
    assert direct_cmd.cleaned_text == "abre o VS Code"


def test_transcribe_filters_silence_via_neural_vad_and_native_endpoints(
    client: TestClient,
) -> None:
    silence_wav = pcm_to_wav(b"\x00\x00" * 4000, sample_rate=16000)
    resp = client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("silence.wav", silence_wav, "audio/wav")},
        data={"language": "pt"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["speech_detected"] is False
    assert body["engine"] == "silero-vad-filtered"
    assert body["text"] == ""

    native_status = client.get("/api/v1/voice/native/status")
    assert native_status.status_code == 200
    assert "neural_vad" in native_status.json()

    cfg = client.put("/api/v1/voice/native/config", json={"require_wake_word": False})
    assert cfg.status_code == 200
    assert cfg.json()["require_wake_word"] is False
    client.put("/api/v1/voice/mode", json={"mode": "proactive"})


@pytest.mark.asyncio
async def test_ambient_brain_listens_and_shares_proactive_opinions(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import AmbientConversationBrain

    brain = AmbientConversationBrain(proactive_cooldown_seconds=10.0)
    responses = iter(
        [
            ("[SILENCIO]", "fake", "fake-model", False),
            ("Na minha opinião, Python com FastAPI continua imbatível para essa API.", "fake", "fake-model", False),
        ]
    )

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return next(responses)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)

    # Whisper noise is ignored
    noise = await brain.evaluate_and_respond(db_session, "Obrigado.")
    assert noise.heard is False
    assert noise.should_speak is False

    # First room phrase -> AI chooses [SILENCIO], but keeps phrase in room buffer
    d1 = await brain.evaluate_and_respond(db_session, "Estava aqui a pensar no projeto novo.")
    assert d1.heard is True
    assert d1.should_speak is False
    assert d1.reason == "ai_chose_silence"
    assert len(brain.recent_heard()) == 1

    # Next room phrase -> AI gives a proactive opinion!
    d2 = await brain.evaluate_and_respond(
        db_session, "Achas que devemos usar Django ou FastAPI para esta API?"
    )
    assert d2.heard is True
    assert d2.should_speak is True
    assert d2.reason == "proactive_opinion"
    assert "FastAPI" in d2.reply_text


def test_voice_mode_and_ambient_endpoints_and_websocket(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import ambient_brain

    ambient_brain.set_mode("proactive")
    ambient_brain._last_proactive_at = 0.0
    ambient_brain.wake_gate.reset_window()

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return ("Pelo que estão a discutir, vale a pena automatizar os testes primeiro.", "fake", "fake-model", False)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)

    mode_resp = client.put("/api/v1/voice/mode", json={"mode": "proactive"})
    assert mode_resp.status_code == 200
    assert mode_resp.json()["listening_mode"] == "proactive"

    eval_resp = client.post(
        "/api/v1/voice/ambient/evaluate",
        json={"text": "Estamos a debater se começamos pelos testes ou pelo deploy."},
    )
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    assert data["should_speak"] is True
    assert "automatizar os testes" in data["reply_text"]

    ambient_brain._last_proactive_at = 0.0
    ambient_brain.wake_gate.reset_window()

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # connection.ready
        ws.send_json(
            {
                "type": "voice.ambient_utterance",
                "content": "E sobre a arquitetura de microserviços, será que compensa?",
            }
        )
        events = [ws.receive_json() for _ in range(5)]
        event_types = {ev["type"] for ev in events}
        assert "voice.ambient.heard" in event_types
        assert "chat.stream.end" in event_types


@pytest.mark.asyncio
async def test_whisper_no_speech_filter_and_self_echo_guard(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import AmbientConversationBrain

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text": "É isso.",
                "segments": [
                    {
                        "text": "É isso.",
                        "no_speech_prob": 0.88,
                        "avg_logprob": -1.4,
                        "compression_ratio": 1.0,
                    }
                ],
            },
        )

    stt = GroqSTTProvider(api_key="test-key", client_factory=_mock_client_factory(handler))
    filtered_text = await stt.transcribe(b"RIFFdata", language="pt")
    assert filtered_text == ""

    brain = AmbientConversationBrain(proactive_cooldown_seconds=10.0)

    async def fake_generate_chat(**_kwargs):  # type: ignore[no-untyped-def]
        return ("Python com FastAPI é excelente para projetos rápidos.", "fake", "fake-model", False)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)
    d1 = await brain.evaluate_and_respond(db_session, "Muquissi, qual framework recomendas?")
    assert d1.should_speak is True

    # Self-echo picked up by mic right after Muquissi finishes speaking must be filtered
    echo = await brain.evaluate_and_respond(
        db_session, "Python com FastAPI é excelente para projetos rápidos"
    )
    assert echo.heard is False
    assert echo.should_speak is False
    assert echo.reason == "self_echo_filtered"


def test_infer_face_mood_emotions_and_system_fatigue() -> None:
    from app.voice.ambient_brain import infer_face_mood

    assert infer_face_mood("Estou tão triste hoje, correu tudo mal.") == "sad"
    assert infer_face_mood("Que cansaço enorme, preciso de dormir.") == "tired"
    assert infer_face_mood("Tudo tranquilo.", {"cpu_percent": 92.0}) == "tired"
    assert infer_face_mood("Parabéns, ficou excelente!") == "happy"
    assert infer_face_mood("Uau, incrível isso!") == "surprised"
    assert infer_face_mood("Como funciona isso?") == "curious"
    assert infer_face_mood("Está tudo certo.") == "neutral"
