"""Background learning: Arcanjo remembers who Carlos is and what they talked about.

After each exchange a fast model extracts durable facts (preferences, people, projects,
plans, how Carlos feels) and stores them as memories. When a conversation goes quiet, it
is summarized into an "episode" so later Arcanjo can say "ontem falámos de...".
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Coroutine
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.ai.base import ChatMessage
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import Conversation, MemoryEntry, Message
from app.database.session import SessionLocal
from app.memory.service import contains_sensitive_secret, memory_service

logger = get_logger("brain.learning")

_CATEGORY_MAP = {
    "perfil": "long_term",
    "facto": "long_term",
    "rotina": "long_term",
    "plano": "long_term",
    "sentimento": "long_term",
    "preferencia": "preference",
    "preferência": "preference",
    "gosto": "preference",
    "pessoa": "person",
    "projeto": "project",
}
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_background: set[asyncio.Task[Any]] = set()


def _enabled() -> bool:
    return bool(get_settings().brain_auto_memory)


def spawn(coro: Coroutine[Any, Any, Any]) -> None:
    """Fire-and-forget a learning job without blocking the conversation."""
    if not _enabled():
        coro.close()
        return
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def _norm(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def _is_duplicate(content: str, existing: list[str]) -> bool:
    words = _norm(content)
    if not words:
        return True
    for other in existing:
        other_words = _norm(other)
        if other_words and len(words & other_words) / len(words | other_words) >= 0.6:
            return True
    return False


async def _ask_brain(db: Any, prompt: str) -> str:
    from app.ai.manager import ai_manager
    from app.voice.ambient_brain import voice_ai_overrides

    reply, *_ = await ai_manager.generate_chat(
        db=db,
        messages=[ChatMessage(role="user", content=prompt)],
        **voice_ai_overrides(),
    )
    return reply


_pending_exchanges: list[tuple[str, str]] = []
_reflect_task: asyncio.Task[Any] | None = None
REFLECT_AFTER_SECONDS = 60.0


def note_exchange(user_text: str, reply_text: str) -> None:
    """Queue an exchange; Arcanjo reflects on all of them once the conversation quiets down.

    One learning call per pause (instead of one per sentence) keeps the free API quota for
    talking, the same way a person sorts out their memories after a conversation.
    """
    global _reflect_task
    if not _enabled() or len(user_text.split()) < 4:
        return
    _pending_exchanges.append((user_text, reply_text))
    if _reflect_task is not None and not _reflect_task.done():
        _reflect_task.cancel()
    _reflect_task = asyncio.create_task(_reflect_later())


async def _reflect_later() -> None:
    await asyncio.sleep(REFLECT_AFTER_SECONDS)
    batch = list(_pending_exchanges)
    _pending_exchanges.clear()
    if not batch:
        return
    users = "\n".join(f"- {u}" for u, _ in batch[-12:])
    replies = "\n".join(f"- {r}" for _, r in batch[-12:])
    await learn_from_exchange(users, replies, min_words=0)


async def learn_from_exchange(user_text: str, reply_text: str, min_words: int = 4) -> int:
    """Extract and store durable facts about Carlos from one exchange. Returns count saved."""
    if len(user_text.split()) < min_words:
        return 0
    db = SessionLocal()
    try:
        recent = list(
            db.scalars(
                select(MemoryEntry).where(MemoryEntry.category != "episode")
                .order_by(MemoryEntry.id.desc()).limit(60)
            ).all()
        )
        known = [m.content for m in recent]
        known_block = "\n".join(f"- {k}" for k in known[:40]) or "(nada ainda)"
        prompt = (
            "És a memória de longo prazo do Arcanjo, a IA pessoal do Carlos. Lê esta troca e "
            "extrai APENAS factos duradouros que valha a pena lembrar daqui a semanas: quem o "
            "Carlos é, gostos, opiniões, pessoas na vida dele (nome + relação), projetos, planos, "
            "datas importantes, rotinas, como se sente sobre algo importante. Ignora conversa "
            "trivial, pedidos pontuais, comandos e qualquer password/chave.\n"
            f"Já sabes:\n{known_block}\n\n"
            f"Carlos disse: {user_text}\nStella respondeu: {reply_text}\n\n"
            'Responde só com JSON: {"memorias": [{"categoria": "perfil|preferencia|pessoa|projeto|plano|rotina|sentimento", '
            '"conteudo": "frase curta na 3.ª pessoa, ex.: O Carlos torce pelo Petro de Luanda."}]}. '
            'Se não houver nada novo: {"memorias": []}'
        )
        raw = await _ask_brain(db, prompt)
        match = _JSON_RE.search(raw)
        if not match:
            return 0
        try:
            items = json.loads(match.group(0)).get("memorias") or []
        except (json.JSONDecodeError, AttributeError):
            return 0

        saved = 0
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("conteudo", "")).strip()
            category = _CATEGORY_MAP.get(str(item.get("categoria", "")).strip().lower(), "long_term")
            if len(content) < 8 or contains_sensitive_secret(content) or _is_duplicate(content, known):
                continue
            memory_service.create_memory(db, category=category, content=content, source="auto")
            known.append(content)
            saved += 1
        if saved:
            logger.info("Aprendi %d coisa(s) nova(s) sobre o Carlos.", saved)
        return saved
    except Exception as exc:  # noqa: BLE001 — learning must never break a conversation
        logger.warning("Falha ao aprender com a conversa: %s", exc)
        return 0
    finally:
        db.close()


def _episode_source(conversation_id: int) -> str:
    return f"auto-episode:{conversation_id}"


async def remember_previous_conversation(new_conversation_id: int) -> bool:
    """When a new conversation starts, store the previous one as an episode (once)."""
    db = SessionLocal()
    try:
        previous = db.scalars(
            select(Conversation.id)
            .where(Conversation.id < new_conversation_id)
            .order_by(Conversation.id.desc())
            .limit(1)
        ).first()
    finally:
        db.close()
    if previous is None:
        return False
    return await summarize_episode(int(previous))


async def summarize_episode(conversation_id: int) -> bool:
    """Turn a finished conversation into a short dated episode memory."""
    db = SessionLocal()
    try:
        already = db.scalars(
            select(MemoryEntry.id).where(MemoryEntry.source == _episode_source(conversation_id))
        ).first()
        if already is not None:
            return False
        rows = list(
            db.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc()).limit(40)
            ).all()
        )
        rows.reverse()
        if sum(1 for r in rows if r.role == "user") < 2:
            return False
        transcript = "\n".join(
            f"{'Carlos' if r.role == 'user' else 'Arcanjo'}: {r.content[:400]}" for r in rows
        )
        when = (rows[-1].created_at or datetime.now()).strftime("%d/%m/%Y")
        prompt = (
            "Resume esta conversa entre o Carlos e o Arcanjo em 1 a 2 frases, como uma lembrança "
            "pessoal (o que falaram, o que ficou decidido ou pendente, o estado de espírito do "
            "Carlos se for relevante). Sem introduções.\n\n"
            f"{transcript}"
        )
        summary = (await _ask_brain(db, prompt)).strip()
        if not summary or contains_sensitive_secret(summary):
            return False
        memory_service.create_memory(
            db,
            category="episode",
            content=f"Em {when}: {summary}",
            source=_episode_source(conversation_id),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao resumir conversa %s: %s", conversation_id, exc)
        return False
    finally:
        db.close()
