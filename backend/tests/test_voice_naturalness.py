"""Voice conversation naturalness: instant wake ack, speech cleanup, voice brain routing."""

from __future__ import annotations

import pytest

from app.voice.linux_listener import clean_for_speech, split_for_speech


def test_clean_for_speech_strips_markdown_lists_urls_and_emojis() -> None:
    raw = "**Feito!** 🚀\n- Abre https://exemplo.com\n1. Corre `pytest`"
    assert clean_for_speech(raw) == "Feito! Abre Corre pytest"


def test_split_for_speech_merges_tiny_fragments() -> None:
    chunks = split_for_speech("Sim. Já está a correr no servidor de testes. Queres que faça deploy?")
    assert chunks == [
        "Sim. Já está a correr no servidor de testes.",
        "Queres que faça deploy?",
    ]


@pytest.mark.asyncio
async def test_wake_word_alone_answers_instantly_without_llm(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import AmbientConversationBrain

    async def must_not_call(**_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM não deve ser chamado só pelo nome")

    monkeypatch.setattr(ai_manager, "generate_chat", must_not_call)
    brain = AmbientConversationBrain(mode="wake_word")
    decision = await brain.evaluate_and_respond(db_session, "Muquissi!")
    assert decision.should_speak is True
    assert decision.reason == "wake_only"
    assert decision.reply_text
    assert brain.wake_gate.is_window_active


@pytest.mark.asyncio
async def test_follow_up_in_window_uses_voice_brain_and_history(
    db_session,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.manager import ai_manager
    from app.core.config import get_settings
    from app.voice.ambient_brain import AmbientConversationBrain

    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "voice_ai_provider", "")
    calls: list[dict] = []

    async def fake_generate_chat(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return ("Resposta.", "groq", "m", False)

    monkeypatch.setattr(ai_manager, "generate_chat", fake_generate_chat)
    brain = AmbientConversationBrain(mode="wake_word")
    await brain.evaluate_and_respond(db_session, "Muquissi, lembra-te que gosto de FastAPI.")
    # Sem dizer o nome: ainda dentro da janela de conversa
    d2 = await brain.evaluate_and_respond(db_session, "E qual é a minha framework favorita?")
    assert d2.should_speak is True
    assert calls[-1]["provider_override"] == "groq"
    history = [m.content for m in calls[-1]["messages"]]
    assert any("FastAPI" in c for c in history)


@pytest.mark.asyncio
async def test_wake_word_mode_ignores_room_talk_outside_window(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    from app.voice.ambient_brain import AmbientConversationBrain

    brain = AmbientConversationBrain(mode="wake_word")
    decision = await brain.evaluate_and_respond(db_session, "Vou ali buscar um café.")
    assert decision.should_speak is False
    assert decision.reason == "wake_word_not_matched"


def test_arcanjo_speaks_serenely_and_proclaims_scripture() -> None:
    from app.voice.edge_tts_provider import scripture_segments

    segs = scripture_segments("Não temas, Carlos. Assim está escrito: «O Senhor é o meu pastor.» Paz seja contigo.")
    assert segs == [
        ("Não temas, Carlos. Assim está escrito:", "Arcanjo"),
        ("O Senhor é o meu pastor.", "Arcanjo-Proclama"),
        ("Paz seja contigo.", "Arcanjo"),
    ]
    assert scripture_segments("Olá", "Muquissi-Mulher") == [("Olá", "Muquissi-Mulher")]


def test_references_are_spoken_as_chapter_and_verse_not_hours():
    from app.voice.edge_tts_provider import speakable_references

    assert speakable_references("Assim está escrito em João 3:16:") == "Assim está escrito em João, capítulo 3, versículo 16:"
    assert speakable_references("Mateus 22:30-32") == "Mateus, capítulo 22, versículos 30 a 32"
    assert speakable_references("chega às 10:30") == "chega às 10:30"


def test_tongues_of_angels_are_proclaimed():
    from app.voice.edge_tts_provider import scripture_segments

    segs = scripture_segments("Inclino-me diante d'Ele. ⟪Elohai shalim ra'avah⟫ Fala-Lhe tu também.")
    assert ("Elohai shalim ra'avah", "Arcanjo-Proclama") in segs
