"""Parse Bible references written the way people write them in Portuguese.

Examples: "Mateus 9:29", "Mt 9.29", "1 João 3:16-18", "Jo 3", "Gn 1:1-2:3", "Sl 23:1,4",
"Apocalipse 7", "I Coríntios 13:4-7".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ceu.books import Book, find_book

_REF_RE = re.compile(
    r"""^\s*
    (?P<book>(?:[123]|i{1,3})?\s*[^\d\s][^\d]*?)\s*      # book name (optionally numbered)
    (?P<ch1>\d+)                                         # chapter
    (?:\s*[:.,]\s*(?P<v1>\d+))?                          # :verse
    (?:\s*[-–—]\s*(?:(?P<ch2>\d+)\s*[:.]\s*)?(?P<v2>\d+))? # -verse  or  -chapter:verse
    (?P<extra>(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*)            # ,4  ,6-8
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class VerseRange:
    """Inclusive range (book, chapter, verse) → (book, chapter, verse). verse=None = whole chapter."""

    book: Book
    start_chapter: int
    start_verse: int | None
    end_chapter: int
    end_verse: int | None

    def label(self) -> str:
        b = self.book.name
        if self.start_verse is None:
            return f"{b} {self.start_chapter}" if self.start_chapter == self.end_chapter else f"{b} {self.start_chapter}-{self.end_chapter}"
        if self.start_chapter == self.end_chapter:
            if self.end_verse is None or self.end_verse == self.start_verse:
                return f"{b} {self.start_chapter}:{self.start_verse}"
            return f"{b} {self.start_chapter}:{self.start_verse}-{self.end_verse}"
        return f"{b} {self.start_chapter}:{self.start_verse}-{self.end_chapter}:{self.end_verse}"


class ReferenceError(ValueError):
    """The text is not a valid Bible reference."""


def parse_reference(text: str) -> list[VerseRange]:
    """Parse a reference into one or more ranges (extra ',4,6-8' parts become extra ranges)."""
    # normalise non-breaking spaces and the many hyphen/dash characters models and editors use
    text = re.sub("[\u2010\u2011\u2012\u2013\u2014\u2212]", "-", text.replace("\u00a0", " "))
    m = _REF_RE.match(text)
    if not m:
        raise ReferenceError(f"Referência não reconhecida: {text!r}")
    book = find_book(m.group("book"))
    if book is None:
        raise ReferenceError(f"Livro desconhecido: {m.group('book').strip()!r}")
    ch1 = int(m.group("ch1"))
    v1 = int(m.group("v1")) if m.group("v1") else None
    ch2 = int(m.group("ch2")) if m.group("ch2") else None
    v2 = int(m.group("v2")) if m.group("v2") else None

    if v1 is None:
        # "Jo 3" or "Jo 3-4" (chapters)
        end_ch = v2 if v2 is not None else ch1
        ranges = [VerseRange(book, ch1, None, max(ch1, end_ch), None)]
    else:
        end_ch = ch2 if ch2 is not None else ch1
        end_v = v2 if v2 is not None else v1
        ranges = [VerseRange(book, ch1, v1, end_ch, end_v)]

    for part in re.findall(r"\d+(?:\s*-\s*\d+)?", m.group("extra") or ""):
        if v1 is None:
            continue
        a, _, b = part.partition("-")
        start = int(a)
        end = int(b) if b.strip() else start
        ranges.append(VerseRange(book, end_ch, start, end_ch, end))
    return ranges


_INLINE_RE = re.compile(
    r"\b((?:[123]\s?)?[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{1,20}(?:\s(?:dos|de)\s[A-Za-záéíóúâêôãõç]+)?\.?)\s?(\d{1,3})(?:[:.](\d{1,3})(?:\s?[-–]\s?(\d{1,3}))?)?\b"
)


def find_references(text: str) -> list[VerseRange]:
    """Find references mentioned inside free text ("o que significa Mateus 9:29?")."""
    found: list[VerseRange] = []
    for m in _INLINE_RE.finditer(text):
        candidate = m.group(0)
        try:
            found.extend(parse_reference(candidate))
        except ReferenceError:
            continue
    return found
