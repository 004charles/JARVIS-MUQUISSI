"""Original languages in the Céu: Hebrew OT and Greek NT word by word, with Strong lexicons.

Source: STEPBible.org data (Tyndale House, Cambridge) — CC BY 4.0
  TAHOT (Translators Amalgamated Hebrew OT), TAGNT (Translators Amalgamated Greek NT),
  TBESH / TBESG (Translators Brief lexicons of Extended Strongs).
Verse numbering follows English/Portuguese Bibles (Hebrew numbering is in brackets in the source),
so words line up with the Bíblia Livre verses. Psalm superscriptions are verse 0.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.ceu.books import BY_ORDINAL
from app.ceu.models import LexiconEntry, OriginalWord
from app.ceu.reference import parse_reference

ATTRIBUTION = "Textos originais e léxicos: STEPBible.org (Tyndale House, Cambridge), CC BY 4.0."

# STEPBible book codes in canonical order → ordinals 1..66
STEP_BOOKS = (
    "Gen Exo Lev Num Deu Jos Jdg Rut 1Sa 2Sa 1Ki 2Ki 1Ch 2Ch Ezr Neh Est Job Psa Pro Ecc Sng Isa Jer Lam Ezk "
    "Dan Hos Jol Amo Oba Jon Mic Nam Hab Zep Hag Zec Mal Mat Mrk Luk Jhn Act Rom 1Co 2Co Gal Eph Php Col 1Th "
    "2Th 1Ti 2Ti Tit Phm Heb Jas 1Pe 2Pe 1Jn 2Jn 3Jn Jud Rev"
).split()
STEP_TO_ORDINAL = {code: i + 1 for i, code in enumerate(STEP_BOOKS)}

_REF_RE = re.compile(r"^([1-3]?[A-Z][a-z]{1,2})\.(\d+)\.(\d+)(?:\([^)]*\))?#(\d+)")
_BRACE_RE = re.compile(r"\{([HG]\d{4,5}[A-Za-z]?)\}")
_STRONG_RE = re.compile(r"^([HG])0*(\d{1,5})([A-Za-z]?)$", re.IGNORECASE)
_GREEK_WORD_RE = re.compile(r"^(.*?)\s*\((.*?)\)\s*$")
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_strong(value: str) -> str | None:
    """'h430' / 'H0430G' / 'g4102' → canonical 'H0430' / 'H0430G' / 'G4102'."""
    m = _STRONG_RE.match(value.strip())
    if not m:
        return None
    return f"{m.group(1).upper()}{int(m.group(2)):04d}{m.group(3).upper()}"


def _clean_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text).replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()[:4000]


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn").lower()


# ------------------------------------------------------------------ import
def parse_tahot_line(line: str) -> dict[str, Any] | None:
    cols = line.rstrip("\n").split("\t")
    if len(cols) < 9:
        return None
    m = _REF_RE.match(cols[0])
    if not m or m.group(1) not in STEP_TO_ORDINAL:
        return None
    brace = _BRACE_RE.search(cols[4])
    strong = brace.group(1) if brace else cols[8].split("_")[0].strip()
    strong = normalize_strong(strong) or strong[:16]
    return {
        "book": STEP_TO_ORDINAL[m.group(1)], "chapter": int(m.group(2)), "verse": int(m.group(3)),
        "position": int(m.group(4)), "language": "he",
        "word": cols[1].replace("/", "").replace("\\", "")[:80], "translit": cols[2].replace("/", "").replace("\\", "")[:80],
        "gloss": re.sub(r"/\s*", " ", cols[3]).strip()[:160], "strong": strong,
        "morph": cols[5][:40], "lemma": "", "editions": "",
    }


def parse_tagnt_line(line: str) -> dict[str, Any] | None:
    cols = line.rstrip("\n").split("\t")
    if len(cols) < 6:
        return None
    m = _REF_RE.match(cols[0])
    if not m or m.group(1) not in STEP_TO_ORDINAL:
        return None
    wm = _GREEK_WORD_RE.match(cols[1])
    word, translit = (wm.group(1), wm.group(2)) if wm else (cols[1], "")
    strong_raw, _, morph = cols[3].partition("=")
    lemma = cols[4].split("=")[0]
    return {
        "book": STEP_TO_ORDINAL[m.group(1)], "chapter": int(m.group(2)), "verse": int(m.group(3)),
        "position": int(m.group(4)), "language": "gr",
        "word": word.strip()[:80], "translit": translit.strip()[:80], "gloss": cols[2].strip()[:160],
        "strong": normalize_strong(strong_raw) or strong_raw[:16], "morph": morph.strip()[:40],
        "lemma": lemma.strip()[:80], "editions": cols[5].strip()[:120],
    }


def parse_lexicon_line(line: str, language: str) -> dict[str, Any] | None:
    cols = line.rstrip("\n").split("\t")
    if len(cols) < 8 or not re.match(r"^[HG]\d{4}", cols[0]):
        return None
    base = re.match(r"[HG]\d{4,5}", cols[0].strip())
    estrong = normalize_strong(base.group(0)) if base else cols[0].strip()[:16]
    dstrong = normalize_strong(cols[1].split("=")[0].strip()) or estrong
    return {
        "strong": dstrong, "estrong": estrong,
        "language": language, "lemma": cols[3].strip()[:80], "translit": cols[4].strip()[:80],
        "morph": cols[5].strip()[:40], "gloss": cols[6].strip()[:160], "definition": _clean_html(cols[7]),
    }


def import_originals(db: Session, folder: Path) -> dict[str, int]:
    counts = {"hebrew_words": 0, "greek_words": 0, "lexicon": 0}
    db.execute(delete(OriginalWord))
    db.execute(delete(LexiconEntry))
    db.commit()
    for pattern, parser, key in (("TAHOT_*.txt", parse_tahot_line, "hebrew_words"), ("TAGNT_*.txt", parse_tagnt_line, "greek_words")):
        for path in sorted(folder.glob(pattern)):
            batch: list[dict[str, Any]] = []
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    row = parser(line)
                    if row:
                        batch.append(row)
                    if len(batch) >= 20000:
                        db.execute(insert(OriginalWord), batch)
                        counts[key] += len(batch)
                        batch = []
            if batch:
                db.execute(insert(OriginalWord), batch)
                counts[key] += len(batch)
            db.commit()
    seen: set[str] = set()
    for pattern, lang in (("TBESH_*.txt", "he"), ("TBESG_*.txt", "gr")):
        rows = []
        for path in sorted(folder.glob(pattern)):
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    row = parse_lexicon_line(line, lang)
                    if row and row["strong"] not in seen:
                        seen.add(row["strong"])
                        rows.append(row)
        for i in range(0, len(rows), 5000):
            db.execute(insert(LexiconEntry), rows[i : i + 5000])
        counts["lexicon"] += len(rows)
        db.commit()
    return counts


# ------------------------------------------------------------------ queries
def lexicon_entry(db: Session, strong: str) -> LexiconEntry | None:
    s = normalize_strong(strong)
    if not s:
        return None
    entry = db.get(LexiconEntry, s)
    if entry is None:
        base = re.sub(r"[A-Z]$", "", s)
        entry = db.scalars(select(LexiconEntry).where(LexiconEntry.estrong == base).order_by(LexiconEntry.strong)).first()
    return entry


def original_text(db: Session, reference: str, max_words: int = 400) -> dict[str, Any]:
    """Words of the original text for a reference, each with its Strong number and short meaning."""
    out_verses = []
    total = 0
    for r in parse_reference(reference):
        q = select(OriginalWord).where(OriginalWord.book == r.book.ordinal)
        if r.start_verse is None:
            q = q.where(OriginalWord.chapter.between(r.start_chapter, r.end_chapter))
        else:
            q = q.where(
                or_(OriginalWord.chapter > r.start_chapter, (OriginalWord.chapter == r.start_chapter) & (OriginalWord.verse >= r.start_verse)),
                or_(OriginalWord.chapter < r.end_chapter, (OriginalWord.chapter == r.end_chapter) & (OriginalWord.verse <= (r.end_verse or 999))),
            )
        words = db.scalars(q.order_by(OriginalWord.chapter, OriginalWord.verse, OriginalWord.position, OriginalWord.id)).all()
        gloss_cache: dict[str, str] = {}
        current = None
        for w in words:
            if total >= max_words:
                break
            key = (w.chapter, w.verse)
            if current is None or current["key"] != key:
                current = {"key": key, "ref": f"{BY_ORDINAL[w.book].name} {w.chapter}:{w.verse}", "words": []}
                out_verses.append(current)
            if w.strong not in gloss_cache:
                e = lexicon_entry(db, w.strong)
                gloss_cache[w.strong] = e.gloss if e else ""
            current["words"].append({
                "word": w.word, "translit": w.translit, "gloss": w.gloss, "strong": w.strong,
                "morph": w.morph, "meaning": gloss_cache[w.strong], "editions": w.editions,
            })
            total += 1
    for v in out_verses:
        v.pop("key", None)
    language = "hebraico" if out_verses and out_verses[0]["words"] and out_verses[0]["words"][0]["strong"].startswith("H") else "grego"
    return {"reference": "; ".join(r.label() for r in parse_reference(reference)), "language": language, "verses": out_verses, "attribution": ATTRIBUTION}


def word_study(db: Session, query: str, samples: int = 6) -> dict[str, Any] | None:
    """Study a word by Strong number ('G4102', 'H430') or by its lemma/transliteration ('pistis', 'agape')."""
    entry = lexicon_entry(db, query)
    if entry is None:
        needle = _strip_accents(query.strip()).replace(".", "").replace("'", "")
        plain = func.lower(func.replace(func.replace(LexiconEntry.translit, ".", ""), "'", ""))
        candidates = db.scalars(
            select(LexiconEntry).where(or_(plain == needle, LexiconEntry.lemma == query.strip())).order_by(LexiconEntry.strong)
        ).all()
        if not candidates:
            # accented transliterations (agapē, hēpsato): compare without diacritics in Python
            pool = db.scalars(select(LexiconEntry).where(plain.like(f"{needle[:2]}%")).limit(3000)).all()
            candidates = [e for e in pool if _strip_accents(e.translit).replace(".", "").replace("'", "") == needle]
        entry = candidates[0] if candidates else None
    if entry is None:
        return None
    base = re.sub(r"[A-Z]$", "", entry.strong)
    occ_filter = or_(OriginalWord.strong == entry.strong, OriginalWord.strong == base)
    count = db.scalar(select(func.count()).select_from(OriginalWord).where(occ_filter)) or 0
    refs = db.execute(
        select(OriginalWord.book, OriginalWord.chapter, OriginalWord.verse).where(occ_filter)
        .group_by(OriginalWord.book, OriginalWord.chapter, OriginalWord.verse)
        .order_by(OriginalWord.book, OriginalWord.chapter, OriginalWord.verse).limit(samples)
    ).all()
    return {
        "strong": entry.strong, "language": "hebraico" if entry.language == "he" else "grego",
        "lemma": entry.lemma, "translit": entry.translit, "morph": entry.morph, "gloss": entry.gloss,
        "definition": entry.definition, "occurrences": int(count),
        "sample_refs": [f"{BY_ORDINAL[b].name} {c}:{v}" for b, c, v in refs], "attribution": ATTRIBUTION,
    }
