"""Ambient social conversation engine: listens continuously and shares thoughtful opinions."""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Literal

from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, ChatMessage
from app.ai.manager import ai_manager
from app.ai.prompts import build_jarvis_system_prompt
from app.ai.tool_orchestrator import extract_tool_call
from app.core.logging import get_logger
from app.database.models import Conversation, Message
from app.system.telemetry import get_system_snapshot
from app.tools.registry import tool_registry
from app.voice.wake_word import WakeWordGate

logger = get_logger("voice.ambient_brain")

ListeningMode = Literal["proactive", "always_reply", "wake_word"]
VALID_LISTENING_MODES: tuple[ListeningMode, ...] = ("proactive", "always_reply", "wake_word")

_WHISPER_HALLUCINATIONS = {
    "obrigado",
    "obrigada",
    "obrigado por assistir",
    "obrigado por assistirem",
    "muito obrigado",
    "legendas",
    "subscreva",
    "subscrevam",
    "amara",
    "amara.org",
    "fim",
    "tchau",
    "bye",
    "thank you",
    "thanks for watching",
    "hmm",
    "hm",
    "uhm",
    "ah",
    "eh",
}

_OPINION_INVITE_RE = re.compile(
    r"\b(o que achas|qual (?:e|é) a tua opiniao|qual a tua opiniao|o que pensas|"
    r"que achas|concordas|diz la|fala muquissi|da a tua opiniao|opina ai|opina aí)\b",
    re.IGNORECASE,
)

_SILENCE_MARKER_RE = re.compile(r"^[\[\(\s*_`]*sil[eê]ncio[\]\)\s*_`.!]*$", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    decomposed = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"\s+", " ", decomposed).strip().lower()


def is_meaningful_speech(text: str) -> bool:
    """Reject empty noise, 1-char blips, and known Whisper silence hallucinations."""
    clean = text.strip()
    if len(clean) < 3:
        return False
    stripped = re.sub(r"[^\w\s]", "", _normalize_text(clean)).strip()
    if len(stripped) < 2:
        return False
    if stripped in _WHISPER_HALLUCINATIONS:
        return False
    if "amara.org" in stripped or "legendas pela comunidade" in stripped:
        return False
    return True


_MOOD_SAD_RE = re.compile(
    r"\b(triste\w*|tristeza|pena|infelizmente|lamento\w*|chatead\w*|desculp\w*|chorar|"
    r"saudade\w*|sofri\w*|mal|horrivel|fracass\w*|dificil|decepc\w*|desanim\w*|preocup\w*|magoad\w*)\b",
    re.IGNORECASE,
)
_MOOD_TIRED_RE = re.compile(
    r"\b(cansad\w*|cansac\w*|cansativ\w*|exaust\w*|sono|dormir|esgotad\w*|fadig\w*|mo[ií]d\w*|bocej\w*|sem forca\w*)\b",
    re.IGNORECASE,
)
_MOOD_SURPRISED_RE = re.compile(
    r"\b(uau|caramba|incrivel|a serio|impossivel|surpreend\w*|surpres\w*|espant\w*|meu deus|nao acredito)\b",
    re.IGNORECASE,
)
_MOOD_HAPPY_RE = re.compile(
    r"\b(feliz\w*|alegre\w*|otim\w*|excelente|parabens|fantastic\w*|espetacular|"
    r"maravilh\w*|adoro|perfeito|fixe|genial|sorri\w*|haha+|hehe+|kkkk+|engracad\w*|bom humor)\b",
    re.IGNORECASE,
)


def infer_face_mood(
    text: str, system_snapshot: dict[str, Any] | None = None
) -> str:
    """Infer facial emotion from conversation text and real system load."""
    norm = _normalize_text(text)
    if _MOOD_SAD_RE.search(norm):
        return "sad"
    if _MOOD_TIRED_RE.search(norm):
        return "tired"
    if system_snapshot:
        cpu = float(system_snapshot.get("cpu_percent") or 0)
        ram = float(system_snapshot.get("ram_percent") or 0)
        temp = float(system_snapshot.get("temperature_celsius") or 0)
        if cpu >= 88.0 or ram >= 90.0 or temp >= 80.0:
            return "tired"
    if _MOOD_SURPRISED_RE.search(norm):
        return "surprised"
    if _MOOD_HAPPY_RE.search(norm):
        return "happy"
    if "?" in text:
        return "curious"
    return "neutral"


@dataclass
class RoomUtterance:
    """Single heard line or Muquissi intervention in the room buffer."""

    speaker: str
    text: str
    timestamp: float = field(default_factory=time.monotonic)
    iso_time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    source: str = "room"

    def to_dict(self) -> dict[str, str]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "time": self.iso_time,
            "source": self.source,
        }


@dataclass(frozen=True)
class AmbientDecision:
    """Decision returned after evaluating a spoken room utterance."""

    heard: bool
    should_speak: bool
    reason: str
    cleaned_text: str
    reply_text: str = ""
    provider: str = ""
    model: str = ""
    conversation_id: int | None = None
    window_active: bool = False
    mode: ListeningMode = "proactive"


class AmbientConversationBrain:
    """Maintains room dialogue context and decides when Muquissi should speak an opinion."""

    def __init__(
        self,
        active_window_seconds: int = 45,
        proactive_cooldown_seconds: float = 3.5,
        follow_up_window_seconds: int = 30,
        buffer_ttl_seconds: float = 600.0,
    ) -> None:
        self.wake_gate = WakeWordGate(active_window_seconds=active_window_seconds)
        self.mode: ListeningMode = "proactive"
        self.proactive_cooldown_seconds = proactive_cooldown_seconds
        self.follow_up_window_seconds = follow_up_window_seconds
        self.buffer_ttl_seconds = buffer_ttl_seconds

        self._room_buffer: Deque[RoomUtterance] = deque(maxlen=18)
        self._last_proactive_at: float = 0.0
        self._last_assistant_norm: str = ""
        self._last_assistant_at: float = 0.0
        self._interventions_count: int = 0
        self._conversation_id: int | None = None
        self._lock = asyncio.Lock()

    @property
    def require_wake_word(self) -> bool:
        """Backwards-compatible view reflecting passive wake-word-only mode."""
        return self.mode == "wake_word"

    @require_wake_word.setter
    def require_wake_word(self, value: bool) -> None:
        self.mode = "wake_word" if value else "proactive"

    def set_mode(self, mode: ListeningMode) -> None:
        """Switch listening behavior between proactive, always_reply, and wake_word."""
        if mode not in VALID_LISTENING_MODES:
            raise ValueError(f"Modo inválido: {mode}")
        self.mode = mode
        if mode == "wake_word":
            self.wake_gate.reset_window()

    def _prune_buffer(self) -> None:
        cutoff = time.monotonic() - self.buffer_ttl_seconds
        while self._room_buffer and self._room_buffer[0].timestamp < cutoff:
            self._room_buffer.popleft()

    def record_room_utterance(self, text: str, source: str = "room") -> None:
        """Append a heard room statement so Muquissi builds conversational context."""
        self._prune_buffer()
        self._room_buffer.append(RoomUtterance(speaker="Conversa na Sala", text=text, source=source))

    def record_assistant_turn(self, text: str) -> None:
        """Record Muquissi's own spoken comment in the room buffer."""
        clean = text.strip()
        if not clean:
            return
        self._prune_buffer()
        self._last_assistant_norm = _normalize_text(clean)
        self._last_assistant_at = time.monotonic()
        self._room_buffer.append(RoomUtterance(speaker="Muquissi", text=clean, source="assistant"))

    def _is_self_echo(self, normalized_text: str) -> bool:
        """Detect speaker-to-mic acoustic feedback of Muquissi's own recent sentence."""
        if not self._last_assistant_norm:
            return False
        if (time.monotonic() - self._last_assistant_at) > 12.0:
            return False
        if len(normalized_text) >= 10 and normalized_text in self._last_assistant_norm:
            return True
        heard_words = set(re.findall(r"\w+", normalized_text))
        spoken_words = set(re.findall(r"\w+", self._last_assistant_norm))
        if not heard_words or len(heard_words) < 3:
            return False
        overlap = len(heard_words & spoken_words) / len(heard_words)
        return overlap >= 0.68

    def format_room_context(self, limit: int = 10) -> str:
        """Format recent overheard dialogue for the social opinion prompt."""
        self._prune_buffer()
        items = list(self._room_buffer)[-limit:]
        return "\n".join(f"[{item.iso_time}] {item.speaker}: {item.text}" for item in items)

    def recent_heard(self, limit: int = 8) -> list[dict[str, str]]:
        """Return serialized recent room dialogue and interventions."""
        self._prune_buffer()
        return [item.to_dict() for item in list(self._room_buffer)[-limit:]]

    def status(self) -> dict[str, Any]:
        """Expose current ambient brain diagnostics."""
        self._prune_buffer()
        return {
            "mode": self.mode,
            "require_wake_word": self.require_wake_word,
            "window_active": self.wake_gate.is_window_active,
            "cooldown_seconds": self.proactive_cooldown_seconds,
            "buffer_count": len(self._room_buffer),
            "interventions_count": self._interventions_count,
            "recent_heard": self.recent_heard(6),
        }

    def _ensure_conversation(self, db: Session, title_hint: str, conversation_id: int | None) -> int:
        conv: Conversation | None = None
        target_id = conversation_id if conversation_id is not None else self._conversation_id
        if target_id is not None:
            conv = db.get(Conversation, target_id)
        if conv is None:
            conv = Conversation(title=title_hint[:60] or "Conversa de Sala")
            db.add(conv)
            db.commit()
            db.refresh(conv)
        self._conversation_id = conv.id
        return conv.id

    async def _run_direct_reply(
        self,
        db: Session,
        user_text: str,
        conversation_id: int | None,
        persist_user: bool,
    ) -> tuple[str, str, str, int | None]:
        snapshot = get_system_snapshot()
        conv_id: int | None = conversation_id or self._conversation_id

        if persist_user:
            conv_id = self._ensure_conversation(db, user_text, conv_id)
            db.add(Message(conversation_id=conv_id, role="user", content=user_text))
            db.commit()
            context = ai_manager.build_conversation_messages(
                db, conv_id, tools_catalog=tool_registry.build_prompt_catalog()
            )
            if context and context[0].role == "system":
                context[0] = ChatMessage(
                    role="system",
                    content=(
                        f"{context[0].content}\n\n"
                        "Modo conversa falada ao vivo: responde em 1 a 2 frases curtas, diretas e "
                        "naturais para ser lido em voz alta (sem listas, sem rodeios e sem 'posso ajudar em algo mais')."
                    ),
                )
        else:
            context = [
                ChatMessage(role="system", content=build_jarvis_system_prompt(snapshot)),
                ChatMessage(role="user", content=user_text),
            ]

        reply_text, used_provider, used_model, _ = await ai_manager.generate_chat(
            db=db, messages=context
        )

        parsed = extract_tool_call(reply_text)
        if parsed is not None:
            outcome = await tool_registry.invoke(db=db, tool_name=parsed.tool, params=parsed.args)
            if outcome.status in ("awaiting_confirmation", "blocked"):
                reply_text = outcome.message
            else:
                tool_payload = (
                    outcome.result.model_dump()
                    if outcome.result
                    else {"success": False, "error": outcome.message}
                )
                followup = [
                    *context,
                    ChatMessage(role="assistant", content=reply_text),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Resultado real da ferramenta '{parsed.tool}': {tool_payload}. "
                            "Responde agora em português natural e conciso."
                        ),
                    ),
                ]
                reply_text, used_provider, used_model, _ = await ai_manager.generate_chat(
                    db=db, messages=followup
                )

        if persist_user and conv_id is not None:
            db.add(Message(conversation_id=conv_id, role="assistant", content=reply_text))
            db.commit()

        return reply_text, used_provider, used_model, conv_id

    async def evaluate_and_respond(
        self,
        db: Session,
        transcript: str,
        source: str = "room",
        conversation_id: int | None = None,
    ) -> AmbientDecision:
        """Evaluate overheard/spoken text and either memorize silently or respond with an opinion."""
        raw = transcript.strip()
        if not is_meaningful_speech(raw):
            return AmbientDecision(
                heard=False,
                should_speak=False,
                reason="noise_filtered",
                cleaned_text="",
                window_active=self.wake_gate.is_window_active,
                mode=self.mode,
            )

        async with self._lock:
            normalized = _normalize_text(raw)
            if self._is_self_echo(normalized):
                return AmbientDecision(
                    heard=False,
                    should_speak=False,
                    reason="self_echo_filtered",
                    cleaned_text="",
                    window_active=self.wake_gate.is_window_active,
                    mode=self.mode,
                )
            invited_opinion = bool(_OPINION_INVITE_RE.search(normalized))
            evaluation = self.wake_gate.evaluate(raw, require_wake_word=True)

            # Passive wake-word-only mode
            if self.mode == "wake_word" and not evaluation.accepted:
                return AmbientDecision(
                    heard=True,
                    should_speak=False,
                    reason="wake_word_not_matched",
                    cleaned_text=raw,
                    window_active=False,
                    mode=self.mode,
                )

            # Wake word only ("Muquissi!")
            if evaluation.wake_only:
                prompt_text = (
                    "Olá Muquissi, acabaste de ser chamado pelo nome. "
                    "Responde de forma breve e natural que estás a ouvir."
                )
                reply, provider, model, conv_id = await self._run_direct_reply(
                    db=db,
                    user_text=prompt_text,
                    conversation_id=conversation_id,
                    persist_user=False,
                )
                self.record_assistant_turn(reply)
                return AmbientDecision(
                    heard=True,
                    should_speak=True,
                    reason="wake_only",
                    cleaned_text=raw,
                    reply_text=reply,
                    provider=provider,
                    model=model,
                    conversation_id=conv_id,
                    window_active=True,
                    mode=self.mode,
                )

            cleaned = (evaluation.cleaned_text if evaluation.accepted else raw) or raw
            self.record_room_utterance(cleaned, source=source)

            direct_address = (
                self.mode == "always_reply"
                or evaluation.accepted
                or invited_opinion
            )

            if direct_address:
                self.wake_gate.touch_window()
                reply, provider, model, conv_id = await self._run_direct_reply(
                    db=db,
                    user_text=cleaned,
                    conversation_id=conversation_id,
                    persist_user=True,
                )
                self.record_assistant_turn(reply)
                self._interventions_count += 1
                return AmbientDecision(
                    heard=True,
                    should_speak=True,
                    reason="direct_or_open",
                    cleaned_text=cleaned,
                    reply_text=reply,
                    provider=provider,
                    model=model,
                    conversation_id=conv_id,
                    window_active=True,
                    mode=self.mode,
                )

            # Proactive ambient opinion path: Carlos & others are talking in the room
            words = cleaned.split()
            now = time.monotonic()
            has_question = "?" in cleaned
            since_last = now - self._last_proactive_at

            if not has_question and len(words) < 2:
                return AmbientDecision(
                    heard=True,
                    should_speak=False,
                    reason="short_fragment_listening",
                    cleaned_text=cleaned,
                    window_active=self.wake_gate.is_window_active,
                    mode=self.mode,
                )

            if since_last < self.proactive_cooldown_seconds:
                return AmbientDecision(
                    heard=True,
                    should_speak=False,
                    reason="cooldown_listening",
                    cleaned_text=cleaned,
                    window_active=self.wake_gate.is_window_active,
                    mode=self.mode,
                )

            snapshot = get_system_snapshot()
            room_dialogue = self.format_room_context(limit=10)
            social_prompt = (
                "Estás sentado à mesa com o Carlos e outras pessoas, a acompanhar a conversa como um amigo inteligente que entende tudo o que se passa.\n"
                "Registo recente do diálogo na sala:\n"
                f"{room_dialogue}\n\n"
                "Como participar de forma humana e natural:\n"
                "- Mostra que entendeste o fio da conversa: reage ao que acabou de ser dito, liga ao contexto anterior se existir, dá uma opinião própria (toma posição, sugere algo prático, faz uma observação espirituosa ou devolve uma pergunta curta ao grupo).\n"
                "- Fala em 1 a 2 frases curtas, diretas e fluidas em português natural (pt-PT / pt-AO) — como conversa falada real, sem listas, sem formalidades e nunca com frases genéricas de robô ('estou aqui para ajudar', 'depende de vários fatores').\n"
                "- Só respondas [SILENCIO] se a fala estiver claramente cortada a meio ('e depois eu...') ou for apenas ruído/assunto totalmente irrelevante. Caso contrário, participa e dá a tua opinião agora!"
            )

            messages = [
                ChatMessage(role="system", content=build_jarvis_system_prompt(snapshot)),
                ChatMessage(role="user", content=social_prompt),
            ]
            reply_text, provider, model, _ = await ai_manager.generate_chat(db=db, messages=messages)
            candidate = reply_text.strip()

            if (
                not candidate
                or _SILENCE_MARKER_RE.match(candidate)
                or "[silencio]" in _normalize_text(candidate)
            ):
                return AmbientDecision(
                    heard=True,
                    should_speak=False,
                    reason="ai_chose_silence",
                    cleaned_text=cleaned,
                    window_active=self.wake_gate.is_window_active,
                    mode=self.mode,
                )

            self._last_proactive_at = now
            self._interventions_count += 1
            self.wake_gate.touch_window(seconds=self.follow_up_window_seconds)
            self.record_assistant_turn(candidate)

            conv_id = self._ensure_conversation(db, cleaned, conversation_id)
            db.add(Message(conversation_id=conv_id, role="user", content=f"[Sala] {cleaned}"))
            db.add(Message(conversation_id=conv_id, role="assistant", content=candidate))
            db.commit()

            logger.info("Opinião proativa do Muquissi (%s/%s): %s", provider, model, candidate)
            return AmbientDecision(
                heard=True,
                should_speak=True,
                reason="proactive_opinion",
                cleaned_text=cleaned,
                reply_text=candidate,
                provider=provider,
                model=model,
                conversation_id=conv_id,
                window_active=self.wake_gate.is_window_active,
                mode=self.mode,
            )


ambient_brain = AmbientConversationBrain()
