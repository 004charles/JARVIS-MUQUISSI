"""O Céu — Bible access: passages by reference, full-text search and related passages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select, text, tuple_
from sqlalchemy.orm import Session

from app.ceu.books import BOOKS, BY_ORDINAL
from app.ceu.models import BibleCrossRef, BibleTranslation, BibleVerse
from app.ceu.reference import VerseRange, parse_reference

DEFAULT_TRANSLATION = "BLIVRE"
FTS_TABLE = "bible_fts"


@dataclass(frozen=True)
class Verse:
    book: int
    chapter: int
    verse: int
    text: str

    @property
    def ref(self) -> str:
        return f"{BY_ORDINAL[self.book].name} {self.chapter}:{self.verse}"

    def to_dict(self) -> dict[str, Any]:
        b = BY_ORDINAL[self.book]
        return {"ref": self.ref, "book": b.name, "book_ordinal": self.book, "chapter": self.chapter, "verse": self.verse, "text": self.text}


def ensure_fts(db: Session) -> None:
    """Full-text index over the verses (SQLite FTS5, accent-insensitive)."""
    if db.bind is None or db.bind.dialect.name != "sqlite":
        return
    db.execute(
        text(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5("
            "text, content='bible_verses', content_rowid='id', tokenize='unicode61 remove_diacritics 2')"
        )
    )
    db.commit()


def rebuild_fts(db: Session) -> None:
    ensure_fts(db)
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(text(f"INSERT INTO {FTS_TABLE}({FTS_TABLE}) VALUES('rebuild')"))
        db.commit()


def attribution(db: Session, translation: str = DEFAULT_TRANSLATION) -> str:
    row = db.get(BibleTranslation, translation)
    return row.attribution if row else ""


def _range_filter(r: VerseRange):
    cond = [BibleVerse.book == r.book.ordinal]
    if r.start_verse is None:
        cond.append(BibleVerse.chapter.between(r.start_chapter, r.end_chapter))
    else:
        start = (r.start_chapter, r.start_verse)
        end = (r.end_chapter, r.end_verse if r.end_verse is not None else 999)
        cond.append(tuple_(BibleVerse.chapter, BibleVerse.verse).between(start, end))
    return and_(*cond)


def get_range(db: Session, r: VerseRange, translation: str = DEFAULT_TRANSLATION) -> list[Verse]:
    rows = db.scalars(
        select(BibleVerse)
        .where(BibleVerse.translation == translation, _range_filter(r))
        .order_by(BibleVerse.chapter, BibleVerse.verse)
    ).all()
    return [Verse(v.book, v.chapter, v.verse, v.text) for v in rows]


def get_passage(db: Session, reference: str, translation: str = DEFAULT_TRANSLATION, max_verses: int = 200) -> dict[str, Any]:
    """Resolve a written reference ("Mt 9:27-31") to the actual verses."""
    ranges = parse_reference(reference)
    verses: list[Verse] = []
    for r in ranges:
        verses.extend(get_range(db, r, translation))
    truncated = len(verses) > max_verses
    return {
        "reference": "; ".join(r.label() for r in ranges),
        "translation": translation,
        "verses": [v.to_dict() for v in verses[:max_verses]],
        "truncated": truncated,
        "attribution": attribution(db, translation),
    }


_WORD_RE = re.compile(r"[\wÀ-ÿ]{2,}", re.UNICODE)
_STOP = {"de", "da", "do", "das", "dos", "e", "o", "a", "os", "as", "que", "em", "um", "uma", "no", "na", "nos", "nas",
         "por", "para", "com", "se", "ao", "aos", "é", "ou", "mais", "como", "sobre", "biblia", "versiculo", "versículo"}


def search(db: Session, query: str, limit: int = 10, translation: str = DEFAULT_TRANSLATION, book: int | None = None) -> list[dict[str, Any]]:
    """Full-text search (all words first; if nothing, any word), best matches first."""
    words = [w for w in _WORD_RE.findall(query.lower()) if w not in _STOP][:12]
    if not words:
        return []
    ensure_fts(db)
    for joiner in (" AND ", " OR "):
        match = joiner.join(f'"{w}"' for w in words)
        sql = (
            f"SELECT v.id, v.book, v.chapter, v.verse, v.text, bm25({FTS_TABLE}) AS score "
            f"FROM {FTS_TABLE} JOIN bible_verses v ON v.id = {FTS_TABLE}.rowid "
            f"WHERE {FTS_TABLE} MATCH :match AND v.translation = :tr"
            + (" AND v.book = :book" if book else "")
            + " ORDER BY score LIMIT :limit"
        )
        params: dict[str, Any] = {"match": match, "tr": translation, "limit": limit}
        if book:
            params["book"] = book
        rows = db.execute(text(sql), params).all()
        if rows:
            return [Verse(r.book, r.chapter, r.verse, r.text).to_dict() for r in rows]
        if len(words) == 1:
            break
    return []


def related(db: Session, reference: str, limit: int = 8, translation: str = DEFAULT_TRANSLATION) -> list[dict[str, Any]]:
    """Cross references for the first verse of a reference, most-voted first, with their text."""
    r = parse_reference(reference)[0]
    verse = r.start_verse or 1
    xrefs = db.scalars(
        select(BibleCrossRef)
        .where(BibleCrossRef.from_book == r.book.ordinal, BibleCrossRef.from_chapter == r.start_chapter, BibleCrossRef.from_verse == verse)
        .order_by(BibleCrossRef.votes.desc())
        .limit(limit)
    ).all()
    out = []
    for x in xrefs:
        target = VerseRange(BY_ORDINAL[x.to_book], x.to_chapter, x.to_verse, x.to_end_chapter, x.to_end_verse)
        vs = get_range(db, target, translation)
        out.append({"ref": target.label(), "votes": x.votes, "text": " ".join(v.text for v in vs[:4])})
    return out


def list_books(db: Session, translation: str = DEFAULT_TRANSLATION) -> list[dict[str, Any]]:
    chapters = dict(
        db.execute(
            text("SELECT book, MAX(chapter) FROM bible_verses WHERE translation = :tr GROUP BY book"), {"tr": translation}
        ).all()
    )
    return [
        {"ordinal": b.ordinal, "name": b.name, "abbrev": b.abbrev, "testament": b.testament, "group": b.group, "chapters": chapters.get(b.ordinal, 0)}
        for b in BOOKS
    ]


def verse_count(db: Session, translation: str = DEFAULT_TRANSLATION) -> int:
    return int(db.execute(text("SELECT COUNT(*) FROM bible_verses WHERE translation = :tr"), {"tr": translation}).scalar() or 0)


__all__ = ["get_passage", "search", "related", "list_books", "verse_count", "rebuild_fts", "ensure_fts"]
