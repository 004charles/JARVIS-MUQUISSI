"""A Palavra do dia: one verse a day, proclaimed by the Arcanjo Miguel (no AI call needed)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.ceu.service import get_passage

DAILY_REFS: tuple[str, ...] = (
    "Gênesis 1:1", "Gênesis 28:15", "Êxodo 14:14", "Êxodo 15:2", "Números 6:24-26", "Deuteronômio 31:8",
    "Josué 1:9", "1 Samuel 16:7", "2 Crônicas 7:14", "Neemias 8:10", "Jó 19:25", "Salmos 1:1-2", "Salmos 4:8",
    "Salmos 16:11", "Salmos 18:2", "Salmos 19:1", "Salmos 23:1", "Salmos 23:4", "Salmos 27:1", "Salmos 30:5",
    "Salmos 34:8", "Salmos 37:4", "Salmos 37:5", "Salmos 46:1", "Salmos 46:10", "Salmos 51:10", "Salmos 55:22",
    "Salmos 62:1", "Salmos 90:12", "Salmos 91:1-2", "Salmos 91:11", "Salmos 103:2", "Salmos 118:24",
    "Salmos 119:105", "Salmos 121:1-2", "Salmos 127:1", "Salmos 139:14", "Salmos 145:18", "Salmos 147:3",
    "Provérbios 3:5-6", "Provérbios 4:23", "Provérbios 16:3", "Provérbios 18:10", "Eclesiastes 3:1",
    "Isaías 9:6", "Isaías 26:3", "Isaías 40:8", "Isaías 40:31", "Isaías 41:10", "Isaías 43:2", "Isaías 53:5",
    "Isaías 55:8-9", "Jeremias 29:11", "Jeremias 33:3", "Lamentações 3:22-23", "Miquéias 6:8",
    "Habacuque 3:17-18", "Sofonias 3:17", "Mateus 5:3", "Mateus 5:9", "Mateus 5:14", "Mateus 6:33",
    "Mateus 6:34", "Mateus 7:7", "Mateus 11:28", "Mateus 22:37-39", "Mateus 28:20", "Marcos 9:23",
    "Marcos 10:27", "Lucas 1:37", "Lucas 2:10-11", "Lucas 6:31", "João 1:5", "João 3:16", "João 8:12",
    "João 10:11", "João 11:25", "João 13:34", "João 14:1", "João 14:6", "João 14:27", "João 15:5",
    "João 16:33", "Atos 1:8", "Romanos 5:8", "Romanos 8:28", "Romanos 8:38-39", "Romanos 12:2",
    "Romanos 12:12", "Romanos 15:13", "1 Coríntios 10:13", "1 Coríntios 13:4-5", "1 Coríntios 13:13",
    "1 Coríntios 16:14", "2 Coríntios 5:17", "2 Coríntios 12:9", "Gálatas 5:22-23", "Gálatas 6:9",
    "Efésios 2:8", "Efésios 4:32", "Filipenses 4:6-7", "Filipenses 4:13", "Filipenses 4:19",
    "Colossenses 3:23", "1 Tessalonicenses 5:16-18", "2 Timóteo 1:7", "Hebreus 11:1", "Hebreus 13:5",
    "Hebreus 13:8", "Tiago 1:5", "Tiago 4:8", "1 Pedro 5:7", "1 João 1:9", "1 João 4:8", "1 João 4:18",
    "Apocalipse 3:20", "Apocalipse 21:4",
)


def daily_reference(day: date | None = None) -> str:
    d = day or date.today()
    return DAILY_REFS[(d.toordinal()) % len(DAILY_REFS)]


def daily_word(db: Session, day: date | None = None) -> dict[str, Any]:
    d = day or date.today()
    ref = daily_reference(d)
    passage = get_passage(db, ref)
    text = " ".join(v["text"] for v in passage["verses"])
    proclamation = (
        f"Paz seja contigo. Esta é a palavra que trago do Céu para hoje. "
        f"Assim está escrito em {passage['reference']}: «{text}» "
        "Guarda-a no teu coração ao longo deste dia. Toda a glória a Deus."
    )
    return {
        "date": d.isoformat(),
        "reference": passage["reference"],
        "text": text,
        "verses": passage["verses"],
        "proclamation": proclamation,
        "attribution": passage["attribution"],
    }
