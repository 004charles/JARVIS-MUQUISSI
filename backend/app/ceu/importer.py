"""Load the Bible into the Céu.

    python -m app.ceu.importer            # import everything found in data/ceu/raw
    python -m app.ceu.importer --check    # print counts only

Idempotent: each run replaces the data of the sources it imports.
Sources (open licences, see data/ceu/raw/*):
- Bíblia Livre (BLIVRE) 2018, from Almeida 1819 — CC BY 4.0 BR (eBible.org "porbr2018" VPL text)
- OpenBible.info cross references — CC BY
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.ceu.books import BY_EBIBLE, BY_OSIS
from app.ceu.models import BibleCrossRef, BibleTranslation, BibleVerse
from app.ceu.service import rebuild_fts, verse_count
from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger
from app.database.session import SessionLocal, init_db

logger = get_logger("ceu.importer")

RAW = PROJECT_ROOT / "data" / "ceu" / "raw"

BLIVRE = {
    "code": "BLIVRE",
    "name": "Bíblia Livre (2018) — atualizada a partir da Almeida 1819",
    "language": "pt-BR",
    "license": "CC BY 4.0 BR",
    "attribution": (
        "Bíblia Livre (BLIVRE), Copyright © Diego Santos, Mario Sérgio e Marco Teles, fevereiro de 2018. "
        "Licença Creative Commons Atribuição 4.0 Brasil (http://creativecommons.org/licenses/by/4.0/br/)."
    ),
    "source_url": "https://ebible.org/porbr2018/",
}

_VPL_RE = re.compile(r"^([1-3]?[A-Z]{2,3})\s+(\d+):(\d+)\s+(.*)$")
_OSIS_RE = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)$")


def import_vpl(db: Session, path: Path, meta: dict) -> int:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _VPL_RE.match(line.strip())
        if not m:
            continue
        book = BY_EBIBLE.get(m.group(1))
        if book is None:
            continue
        verse_text = m.group(4).strip()
        if not verse_text:
            continue
        rows.append(
            {"translation": meta["code"], "book": book.ordinal, "chapter": int(m.group(2)), "verse": int(m.group(3)), "text": verse_text}
        )
    db.execute(delete(BibleVerse).where(BibleVerse.translation == meta["code"]))
    db.merge(BibleTranslation(**meta))
    for i in range(0, len(rows), 5000):
        db.execute(insert(BibleVerse), rows[i : i + 5000])
    db.commit()
    return len(rows)


def _osis(ref: str):
    m = _OSIS_RE.match(ref)
    if not m:
        return None
    book = BY_OSIS.get(m.group(1))
    return (book.ordinal, int(m.group(2)), int(m.group(3))) if book else None


def import_cross_refs(db: Session, path: Path) -> int:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        src = _osis(parts[0])
        a, _, b = parts[1].partition("-")
        start = _osis(a)
        end = _osis(b) if b else start
        if not src or not start or not end:
            continue
        try:
            votes = int(parts[2])
        except ValueError:
            continue
        if votes < 0:
            continue  # community voted it irrelevant
        rows.append(
            {
                "from_book": src[0], "from_chapter": src[1], "from_verse": src[2],
                "to_book": start[0], "to_chapter": start[1], "to_verse": start[2],
                "to_end_chapter": end[1], "to_end_verse": end[2], "votes": votes,
            }
        )
    db.execute(delete(BibleCrossRef))
    for i in range(0, len(rows), 10000):
        db.execute(insert(BibleCrossRef), rows[i : i + 10000])
    db.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importar a Bíblia para o Céu")
    parser.add_argument("--check", action="store_true", help="só mostrar contagens")
    args = parser.parse_args(argv)
    init_db()
    db = SessionLocal()
    try:
        if not args.check:
            vpl = RAW / "porbr2018" / "porbr2018_vpl.txt"
            if vpl.exists():
                n = import_vpl(db, vpl, BLIVRE)
                print(f"Bíblia Livre: {n} versículos")
            else:
                print(f"Em falta: {vpl}")
            xref = RAW / "openbible" / "cross_references.txt"
            if xref.exists():
                print(f"Referências cruzadas: {import_cross_refs(db, xref)}")
            step = RAW / "stepbible"
            if step.exists():
                from app.ceu.originals import import_originals

                c = import_originals(db, step)
                print(f"Originais: {c['hebrew_words']} palavras hebraicas, {c['greek_words']} gregas, {c['lexicon']} entradas de léxico")
            rebuild_fts(db)
            print("Índice de pesquisa reconstruído.")
        print(f"Total BLIVRE na base: {verse_count(db)} versículos")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
