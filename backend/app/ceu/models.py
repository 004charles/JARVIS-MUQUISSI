"""O Céu — knowledge base tables, starting with the Bible."""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class BibleTranslation(Base):
    """A Bible text loaded into the Céu, with the licence/attribution it must be shown with."""

    __tablename__ = "bible_translations"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. BLIVRE
    name: Mapped[str] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(16), default="pt")
    license: Mapped[str] = mapped_column(String(120))
    attribution: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(300), default="")


class BibleVerse(Base):
    """One verse of one translation. `book` is the canonical ordinal (1 = Gênesis … 66 = Apocalipse)."""

    __tablename__ = "bible_verses"
    __table_args__ = (
        UniqueConstraint("translation", "book", "chapter", "verse", name="uq_bible_verse"),
        Index("ix_bible_verse_lookup", "translation", "book", "chapter", "verse"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    translation: Mapped[str] = mapped_column(String(16), index=True)
    book: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[int] = mapped_column(Integer)
    verse: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class BibleCrossRef(Base):
    """A related passage (OpenBible.info, CC BY), ranked by community votes."""

    __tablename__ = "bible_cross_refs"
    __table_args__ = (Index("ix_bible_xref_from", "from_book", "from_chapter", "from_verse"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_book: Mapped[int] = mapped_column(Integer)
    from_chapter: Mapped[int] = mapped_column(Integer)
    from_verse: Mapped[int] = mapped_column(Integer)
    to_book: Mapped[int] = mapped_column(Integer)
    to_chapter: Mapped[int] = mapped_column(Integer)
    to_verse: Mapped[int] = mapped_column(Integer)
    to_end_chapter: Mapped[int] = mapped_column(Integer)
    to_end_verse: Mapped[int] = mapped_column(Integer)
    votes: Mapped[int] = mapped_column(Integer, default=0)


class OriginalWord(Base):
    """One word of the original text (Hebrew OT / Greek NT) — STEPBible TAHOT/TAGNT, CC BY 4.0."""

    __tablename__ = "bible_original_words"
    __table_args__ = (Index("ix_bible_orig_verse", "book", "chapter", "verse", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[int] = mapped_column(Integer)
    verse: Mapped[int] = mapped_column(Integer)  # 0 = psalm superscription
    position: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(2))  # he | gr
    word: Mapped[str] = mapped_column(String(80))
    translit: Mapped[str] = mapped_column(String(80), default="")
    gloss: Mapped[str] = mapped_column(String(160), default="")  # literal English gloss
    strong: Mapped[str] = mapped_column(String(16), index=True)  # main (disambiguated) Strong, e.g. H0430G
    morph: Mapped[str] = mapped_column(String(40), default="")
    lemma: Mapped[str] = mapped_column(String(80), default="")
    editions: Mapped[str] = mapped_column(String(120), default="")  # Greek: NA28+TR+Byz...


class LexiconEntry(Base):
    """Brief lexicon of extended Strong numbers (STEPBible TBESH/TBESG, CC BY 4.0)."""

    __tablename__ = "bible_lexicon"

    strong: Mapped[str] = mapped_column(String(16), primary_key=True)  # dStrong, e.g. H0430G
    estrong: Mapped[str] = mapped_column(String(16), index=True)  # base number, e.g. H0430
    language: Mapped[str] = mapped_column(String(2))
    lemma: Mapped[str] = mapped_column(String(80))
    translit: Mapped[str] = mapped_column(String(80), default="")
    morph: Mapped[str] = mapped_column(String(40), default="")
    gloss: Mapped[str] = mapped_column(String(160), default="")
    definition: Mapped[str] = mapped_column(Text, default="")
