"""Visões do Céu: when the Arcanjo speaks of a biblical person, place or event, a "vision" opens on
screen — a Gustave Doré engraving (The Holy Bible, 1866, public domain) with the key moments, each one
a real verse read from the Céu (never an invented summary).
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any

from app.core.config import PROJECT_ROOT

DORE_DIRS = (PROJECT_ROOT / "frontend" / "dist" / "assets" / "dore", PROJECT_ROOT / "frontend" / "public" / "assets" / "dore")
DORE_CREDIT = "Gustave Doré, A Bíblia Sagrada (1866) — domínio público"

# Portuguese biblical names/terms → English words used in the Doré plate titles
PT_EN = {
    "noe": "noah ark flood dove", "arca": "ark", "diluvio": "flood deluge water", "pomba": "dove", "adao": "adam", "eva": "eve",
    "eden": "eden", "caim": "cain", "abel": "abel", "criacao": "creation", "babel": "babel tower", "abraao": "abraham",
    "isaque": "isaac", "sacrificio": "sacrifice offering trial faith", "jaco": "jacob", "rebeca": "rebekah", "sara": "sarah", "agar": "hagar", "ismael": "ishmael",
    "lo": "lot", "sodoma": "sodom", "jose": "joseph", "egito": "egypt", "moises": "moses", "farao": "pharaoh",
    "mar vermelho": "red sea egyptians drown", "travessia": "sea drown", "pragas": "plague", "sinai": "sinai mount", "sarca": "bush", "aarao": "aaron", "mandamentos": "commandments tables law",
    "bezerro": "calf", "josue": "joshua", "jerico": "jericho", "gideao": "gideon", "sansao": "samson", "dalila": "delilah",
    "rute": "ruth", "noemi": "naomi", "samuel": "samuel", "saul": "saul", "davi": "david", "golias": "goliath",
    "salomao": "solomon", "templo": "temple", "elias": "elijah", "eliseu": "elisha", "jezabel": "jezebel",
    "jonas": "jonah", "baleia": "whale", "daniel": "daniel", "leoes": "lions", "ester": "esther", "jo": "job",
    "isaias": "isaiah", "jeremias": "jeremiah", "ezequiel": "ezekiel", "nabucodonosor": "nebuchadnezzar",
    "jesus": "jesus christ", "cristo": "christ", "maria": "mary", "nascimento": "nativity birth", "pastores": "shepherds",
    "magos": "magi wise men", "batismo": "baptism", "joao batista": "john baptist", "tentacao": "temptation",
    "sermao": "sermon mount", "lazaro": "lazarus", "ceia": "supper", "getsemani": "gethsemane", "judas": "judas",
    "pedro": "peter", "cruz": "cross crucifixion", "crucificacao": "crucifixion", "ressurreicao": "resurrection",
    "ascensao": "ascension", "paulo": "paul", "estevao": "stephen", "apocalipse": "apocalypse revelation",
    "anjo": "angel", "anjos": "angels", "miguel": "michael", "gabriel": "gabriel", "dragao": "dragon",
    "jerusalem": "jerusalem", "milagre": "miracle", "paraboa": "parable", "filho prodigo": "prodigal son",
    "samaritano": "samaritan", "tempestade": "storm tempest", "agua": "water", "vinho": "wine",
}
_STOP = {"the", "of", "and", "a", "in", "to", "his", "is", "by", "at", "on", "with", "from", "for", "are", "out", "o", "a", "de"}


def _plain(text: str) -> str:
    t = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t.lower())).strip()


@lru_cache(maxsize=1)
def dore_index() -> tuple[dict[str, Any], ...]:
    for folder in DORE_DIRS:
        idx = folder / "index.json"
        if idx.exists():
            return tuple(json.loads(idx.read_text(encoding="utf-8")))
    return ()


def _expand(query: str) -> set[str]:
    q = _plain(query)
    words = set(q.split())
    for pt, en in PT_EN.items():
        if re.search(rf"\b{re.escape(pt)}\b", q):
            words.update(en.split())
    return {w for w in words if w not in _STOP and len(w) > 1}


def find_engraving(query: str) -> dict[str, Any] | None:
    """Best Doré plate for a topic ('Noé arca dilúvio', 'Noah ark'…), or None."""
    words = _expand(query)
    if not words:
        return None
    best, best_score = None, 0.0
    for plate in dore_index():
        title_words = set(_plain(plate["title"]).split()) - _STOP
        hits = len(words & title_words)
        if hits == 0:
            continue
        score = hits + hits / max(len(title_words), 1)  # prefer specific titles
        if score > best_score:
            best, best_score = plate, score
    return best


def build_vision(db: Any, title: str, references: list[str], image_query: str) -> dict[str, Any]:
    """Assemble a vision: verified verses for each reference + the matching engraving."""
    from app.ceu.reference import ReferenceError
    from app.ceu.service import get_passage

    facts = []
    for ref in references[:6]:
        try:
            p = get_passage(db, str(ref), max_verses=6)
        except ReferenceError:
            continue
        if p["verses"]:
            facts.append({"ref": p["reference"], "text": " ".join(v["text"] for v in p["verses"])})
    plate = find_engraving(f"{image_query} {title}")
    image = (
        {"url": f"/assets/dore/{plate['file']}", "caption": plate["title"], "credit": DORE_CREDIT, "source": plate.get("source", "")}
        if plate
        else None
    )
    return {"title": title.strip()[:80], "image": image, "facts": facts}
