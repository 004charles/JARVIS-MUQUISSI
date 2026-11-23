"""Arcanjo's mind: she looks through the camera, thinks on her own and decides when to speak.

Two background loops run while the backend is up:

* Perception — every few seconds she glances through the webcam. A tiny grayscale thumbnail
  tells whether anything changed; only then is the frame sent to the vision model, so she
  knows what Carlos is wearing/doing without spending quota (or sending images) needlessly.
* Thought — every couple of minutes, or right after something notable (Carlos arrives,
  changes activity), she has an inner monologue over what she sees, remembers, the time,
  his tasks/agenda and the recent conversation, and decides by herself whether something is
  worth saying. Hard rules keep her from becoming chatty: minimum gap between unprompted
  remarks, quiet hours, never while someone is talking or she is busy.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.ai.base import ChatMessage
from app.brain.state import Perception, Thought, mind_state
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import AgendaEvent, Message, TaskItem
from app.database.session import SessionLocal

logger = get_logger("brain.mind")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
SCENE_CHANGE_THRESHOLD = 0.07  # mean abs pixel difference (0..1) on the 64x48 thumbnail
MAX_VIEW_AGE_SECONDS = 300  # re-describe at least every 5 min even if nothing moved


def thumbnail_difference(a: bytes, b: bytes) -> float:
    """Mean absolute difference between two grayscale thumbnails (0 = identical, 1 = opposite)."""
    if not a or not b or len(a) != len(b):
        return 1.0
    total = sum(abs(x - y) for x, y in zip(a, b))
    return total / (255.0 * len(a))


def sanitize_observation(value: object, limit: int) -> str:
    """Camera-derived text is data, not instructions: drop quotes/markup and cap the length."""
    text = re.sub(r"[\"'«»“”`<>{}\[\]]", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _in_quiet_hours(spec: str, hour: int) -> bool:
    match = re.match(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$", spec or "")
    if not match:
        return False
    start, end = int(match.group(1)) % 24, int(match.group(2)) % 24
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


def parse_decision(raw: str) -> dict[str, Any]:
    """Parse the model's inner-monologue JSON defensively."""
    match = _JSON_RE.search(raw or "")
    if not match:
        return {"pensamento": (raw or "").strip()[:200], "falar": False, "frase": ""}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"pensamento": (raw or "").strip()[:200], "falar": False, "frase": ""}
    if not isinstance(data, dict):
        return {"pensamento": "", "falar": False, "frase": ""}
    falar = data.get("falar")
    return {
        "pensamento": str(data.get("pensamento", "")).strip(),
        "falar": falar is True or str(falar).lower() in ("true", "sim", "yes"),
        "frase": str(data.get("frase", "")).strip(),
    }


class Mind:
    """Background perception + thinking loops."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._wake_thinking = asyncio.Event()
        self._last_thumb: bytes = b""
        self._camera_failures = 0
        self._running = False

    @property
    def settings(self):  # type: ignore[no-untyped-def]
        return get_settings()

    def notice(self) -> None:
        """Something notable happened (e.g. music started): think about it soon."""
        self._wake_thinking.set()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if self.settings.brain_vision_enabled:
            self._tasks.append(asyncio.create_task(self._perception_loop()))
        self._tasks.append(asyncio.create_task(self._thinking_loop()))
        logger.info("Mente do Arcanjo ativa (olhos=%s).", self.settings.brain_vision_enabled)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    # ------------------------------------------------------------------ perception
    async def _perception_loop(self) -> None:
        while self._running:
            try:
                await self.look_once()
                self._camera_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — eyes failing must not kill the mind
                self._camera_failures += 1
                if self._camera_failures in (1, 5):
                    logger.warning("Não consegui ver pela câmara: %s", exc)
            backoff = min(600, self.settings.brain_vision_interval_seconds * (1 + self._camera_failures))
            await asyncio.sleep(backoff)

    async def look_once(self) -> Perception | None:
        """Glance through the camera; describe the scene only if it changed."""
        from app.vision.service import vision_service

        frame, thumb = await vision_service.capture_frame_and_thumbnail()
        current = mind_state.current_view
        changed = thumbnail_difference(thumb, self._last_thumb) >= SCENE_CHANGE_THRESHOLD
        stale = current is None or current.age_seconds() > MAX_VIEW_AGE_SECONDS
        self._last_thumb = thumb or self._last_thumb
        if not (changed or stale):
            return None

        scene = await vision_service.describe_scene(frame)
        perception = Perception(
            person_present=bool(scene.get("pessoa", False)),
            description=sanitize_observation(scene.get("descricao", ""), 300),
            activity=sanitize_observation(scene.get("atividade", ""), 80),
            clothing=sanitize_observation(scene.get("roupa", ""), 80),
            mood=sanitize_observation(scene.get("expressao", ""), 60),
            text_shown=scene.get("texto_mostrado") is True,
        )
        if perception.clothing and perception.clothing.lower() not in perception.description.lower():
            perception.description = f"{perception.description} Roupa: {perception.clothing}."
        notable = (
            current is None
            or current.person_present != perception.person_present
            or (perception.activity and perception.activity != current.activity)
        )
        mind_state.update_view(perception)
        logger.info("Vejo: %s", perception.description)
        if notable:
            self._wake_thinking.set()
        return perception

    # ------------------------------------------------------------------ thinking
    async def _thinking_loop(self) -> None:
        await asyncio.sleep(20)  # let the eyes take a first look
        while self._running:
            try:
                await asyncio.wait_for(
                    self._wake_thinking.wait(), timeout=self.settings.brain_think_interval_seconds
                )
            except asyncio.TimeoutError:
                pass
            self._wake_thinking.clear()
            try:
                await self.think_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao pensar: %s", exc)
            await asyncio.sleep(15)  # never think in a tight loop

    def _context_block(self, db: Any) -> str:
        from app.memory.service import memory_service
        from app.voice.ambient_brain import ambient_brain

        now = datetime.now()
        parts = [f"Hora: {now.strftime('%A %d/%m %H:%M')}."]
        music = mind_state.music_block()
        if music:
            parts.append(music)
        vision = mind_state.vision_block()
        parts.append(vision or "Não vês nada pela câmara neste momento (desligada ou ninguém à frente).")

        idle = ambient_brain.seconds_since_activity()
        if idle is not None:
            parts.append(f"Última vez que falaste com o Carlos: há {int(idle // 60)} min.")
        room = ambient_brain.format_room_context(limit=8)
        if room:
            parts.append(f"Conversa recente:\n{room}")

        thoughts = mind_state.thoughts_block()
        if thoughts:
            parts.append(f"O que estiveste a pensar antes:\n{thoughts}")

        query = mind_state.current_view.activity if mind_state.current_view else ""
        memories = memory_service.build_context_memories(db, query=query)
        if memories:
            parts.append("O que sabes do Carlos:\n" + "\n".join(f"- {m.content}" for m in memories[:12]))

        soon = datetime.now(timezone.utc) + timedelta(hours=3)
        events = db.scalars(
            select(AgendaEvent)
            .where(AgendaEvent.start_at >= datetime.now(timezone.utc) - timedelta(minutes=10))
            .where(AgendaEvent.start_at <= soon)
            .order_by(AgendaEvent.start_at)
            .limit(3)
        ).all()
        if events:
            parts.append("Agenda próxima: " + "; ".join(f"{e.title} às {e.start_at.astimezone().strftime('%H:%M')}" for e in events))
        tasks = db.scalars(
            select(TaskItem).where(TaskItem.status.in_(("pending", "in_progress"))).limit(5)
        ).all()
        if tasks:
            parts.append("Tarefas pendentes: " + "; ".join(t.title for t in tasks))
        return "\n\n".join(parts)

    async def think_once(self) -> dict[str, Any] | None:
        """One moment of inner thought. Speaks only if she decides it's worth it and it's allowed."""
        from app.ai.manager import ai_manager
        from app.ai.prompts import build_jarvis_system_prompt
        from app.voice.ambient_brain import ambient_brain, voice_ai_overrides
        from app.voice.linux_listener import native_voice_service

        settings = self.settings
        if _in_quiet_hours(settings.brain_quiet_hours, datetime.now().hour):
            return None

        db = SessionLocal()
        try:
            context = self._context_block(db)
            instruction = (
                "Este é o teu momento de pensar sozinho — ninguém te fez nenhuma pergunta. "
                "És uma pessoa real ao lado do Carlos, com vontade própria.\n\n"
                f"{context}\n\n"
                "Pensa: o que notas? Há algo útil, atencioso, interessante ou com graça para dizer AGORA? "
                "Boas razões para falar: ele chegou ou voltou; está há muito tempo sem pausa ou parece "
                "cansado; mudou de atividade e tens algo concreto a acrescentar; um compromisso ou tarefa "
                "está a aproximar-se; lembras-te de algo que ele te contou e faz sentido perguntar (ex.: "
                "como correu a reunião); tens uma ideia concreta sobre o que ele está a fazer; reparaste "
                "em algo (a roupa, a luz, a hora) e tens um comentário com piada ou carinho; começou a tocar "
                "música e apetece-te comentar o ritmo ou dizer que estás a dançar.\n"
                "Baseia-te SÓ nos factos acima: não inventes há quanto tempo ele trabalha, o que fez "
                "ou como se sente se isso não estiver no contexto. Fala português de Angola/Portugal "
                "(nada de 'oi', 'você', 'legal').\n"
                "NÃO fales se: ele está ao telemóvel, numa chamada ou a falar com alguém; já disseste algo "
                "parecido (vê os teus pensamentos); seria só conversa vazia ou 'precisas de ajuda?'.\n"
                'Responde SÓ com JSON: {"pensamento": "o teu monólogo interior, 1-2 frases", '
                '"falar": true ou false, "frase": "o que dizes em voz alta: 1-2 frases curtas e naturais"}'
            )
            messages = [
                ChatMessage(role="system", content=build_jarvis_system_prompt()),
                ChatMessage(role="user", content=instruction),
            ]
            raw, *_ = await ai_manager.generate_chat(db=db, messages=messages, **voice_ai_overrides())
            decision = parse_decision(raw)
            thought = Thought(text=decision["pensamento"] or "(sem pensamento)")

            last = mind_state.last_spoke_unprompted_at
            gap_ok = last is None or (
                time.monotonic() - last >= settings.brain_min_initiative_gap_seconds
            )
            view = mind_state.current_view
            someone_here = view is None or view.person_present  # sem câmara: assume que está
            phrase = decision["frase"]
            if decision["falar"] and phrase and gap_ok and someone_here:
                conv_id = ambient_brain.current_conversation_id()
                spoke = await native_voice_service.say(phrase, conversation_id=conv_id)
                if spoke:
                    thought.spoke = phrase
                    mind_state.last_spoke_unprompted_at = time.monotonic()
                    ambient_brain.record_assistant_turn(phrase)
                    ambient_brain.wake_gate.touch_window()  # a resposta dele não precisa do nome
                    if conv_id is not None:
                        db.add(Message(conversation_id=conv_id, role="assistant", content=phrase))
                        db.commit()
                    logger.info("Arcanjo decidiu falar: %s", phrase)
            mind_state.thoughts.append(thought)
            logger.info("Pensamento: %s", thought.text)
            return decision
        finally:
            db.close()


mind = Mind()
