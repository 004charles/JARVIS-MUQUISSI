"""Canonical catalogue of the 66 books of the Bible (Protestant canon).

Each book links the source codes used by the data sets we import (eBible VPL codes and OSIS ids
used by OpenBible.info cross references) to its Portuguese name, common abbreviations, testament
and literary group.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Book:
    ordinal: int
    ebible: str
    osis: str
    name: str
    abbrev: str
    testament: str  # "AT" (Antigo) | "NT" (Novo)
    group: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


_GROUPS = [
    (range(1, 6), "Pentateuco"),
    (range(6, 18), "Livros Históricos"),
    (range(18, 23), "Livros Poéticos"),
    (range(23, 28), "Profetas Maiores"),
    (range(28, 40), "Profetas Menores"),
    (range(40, 44), "Evangelhos"),
    (range(44, 45), "Histórico (Atos)"),
    (range(45, 58), "Epístolas Paulinas"),
    (range(58, 66), "Epístolas Gerais"),
    (range(66, 67), "Profético (Apocalipse)"),
]

# ordinal, eBible, OSIS, Portuguese name, abbreviation, extra aliases
_RAW: list[tuple[int, str, str, str, str, tuple[str, ...]]] = [
    (1, "GEN", "Gen", "Gênesis", "Gn", ("Genesis", "Génesis", "Gen")),
    (2, "EXO", "Exod", "Êxodo", "Ex", ("Exodo", "Êx")),
    (3, "LEV", "Lev", "Levítico", "Lv", ("Levitico", "Lev")),
    (4, "NUM", "Num", "Números", "Nm", ("Numeros", "Num")),
    (5, "DEU", "Deut", "Deuteronômio", "Dt", ("Deuteronomio", "Deuteronómio", "Deut")),
    (6, "JOS", "Josh", "Josué", "Js", ("Josue",)),
    (7, "JDG", "Judg", "Juízes", "Jz", ("Juizes",)),
    (8, "RUT", "Ruth", "Rute", "Rt", ()),
    (9, "1SA", "1Sam", "1 Samuel", "1Sm", ("1Samuel", "I Samuel")),
    (10, "2SA", "2Sam", "2 Samuel", "2Sm", ("2Samuel", "II Samuel")),
    (11, "1KI", "1Kgs", "1 Reis", "1Rs", ("1Reis", "I Reis")),
    (12, "2KI", "2Kgs", "2 Reis", "2Rs", ("2Reis", "II Reis")),
    (13, "1CH", "1Chr", "1 Crônicas", "1Cr", ("1 Cronicas", "1 Crónicas", "I Crônicas")),
    (14, "2CH", "2Chr", "2 Crônicas", "2Cr", ("2 Cronicas", "2 Crónicas", "II Crônicas")),
    (15, "EZR", "Ezra", "Esdras", "Ed", ("Esd",)),
    (16, "NEH", "Neh", "Neemias", "Ne", ()),
    (17, "EST", "Esth", "Ester", "Et", ()),
    (18, "JOB", "Job", "Jó", "Jó", ("Jo ", "Job")),
    (19, "PSA", "Ps", "Salmos", "Sl", ("Salmo", "Sal")),
    (20, "PRO", "Prov", "Provérbios", "Pv", ("Proverbios", "Prov")),
    (21, "ECC", "Eccl", "Eclesiastes", "Ec", ("Ecl",)),
    (22, "SOL", "Song", "Cânticos", "Ct", ("Canticos", "Cantares", "Cântico dos Cânticos", "Cantico dos Canticos")),
    (23, "ISA", "Isa", "Isaías", "Is", ("Isaias",)),
    (24, "JER", "Jer", "Jeremias", "Jr", ("Jer",)),
    (25, "LAM", "Lam", "Lamentações", "Lm", ("Lamentacoes", "Lam")),
    (26, "EZE", "Ezek", "Ezequiel", "Ez", ()),
    (27, "DAN", "Dan", "Daniel", "Dn", ("Dan",)),
    (28, "HOS", "Hos", "Oséias", "Os", ("Oseias",)),
    (29, "JOE", "Joel", "Joel", "Jl", ()),
    (30, "AMO", "Amos", "Amós", "Am", ("Amos",)),
    (31, "OBA", "Obad", "Obadias", "Ob", ("Abdias",)),
    (32, "JON", "Jonah", "Jonas", "Jn", ()),
    (33, "MIC", "Mic", "Miquéias", "Mq", ("Miqueias",)),
    (34, "NAH", "Nah", "Naum", "Na", ()),
    (35, "HAB", "Hab", "Habacuque", "Hc", ()),
    (36, "ZEP", "Zeph", "Sofonias", "Sf", ()),
    (37, "HAG", "Hag", "Ageu", "Ag", ()),
    (38, "ZEC", "Zech", "Zacarias", "Zc", ()),
    (39, "MAL", "Mal", "Malaquias", "Ml", ()),
    (40, "MAT", "Matt", "Mateus", "Mt", ()),
    (41, "MAR", "Mark", "Marcos", "Mc", ()),
    (42, "LUK", "Luke", "Lucas", "Lc", ()),
    (43, "JOH", "John", "João", "Jo", ("Joao",)),
    (44, "ACT", "Acts", "Atos", "At", ("Actos", "Atos dos Apóstolos", "Actos dos Apóstolos")),
    (45, "ROM", "Rom", "Romanos", "Rm", ()),
    (46, "1CO", "1Cor", "1 Coríntios", "1Co", ("1 Corintios", "I Coríntios")),
    (47, "2CO", "2Cor", "2 Coríntios", "2Co", ("2 Corintios", "II Coríntios")),
    (48, "GAL", "Gal", "Gálatas", "Gl", ("Galatas",)),
    (49, "EPH", "Eph", "Efésios", "Ef", ("Efesios",)),
    (50, "PHI", "Phil", "Filipenses", "Fp", ("Fl",)),
    (51, "COL", "Col", "Colossenses", "Cl", ()),
    (52, "1TH", "1Thess", "1 Tessalonicenses", "1Ts", ("I Tessalonicenses",)),
    (53, "2TH", "2Thess", "2 Tessalonicenses", "2Ts", ("II Tessalonicenses",)),
    (54, "1TI", "1Tim", "1 Timóteo", "1Tm", ("1 Timoteo", "I Timóteo")),
    (55, "2TI", "2Tim", "2 Timóteo", "2Tm", ("2 Timoteo", "II Timóteo")),
    (56, "TIT", "Titus", "Tito", "Tt", ()),
    (57, "PHM", "Phlm", "Filemom", "Fm", ("Filémon", "Filemon")),
    (58, "HEB", "Heb", "Hebreus", "Hb", ()),
    (59, "JAM", "Jas", "Tiago", "Tg", ()),
    (60, "1PE", "1Pet", "1 Pedro", "1Pe", ("I Pedro",)),
    (61, "2PE", "2Pet", "2 Pedro", "2Pe", ("II Pedro",)),
    (62, "1JO", "1John", "1 João", "1Jo", ("1 Joao", "I João")),
    (63, "2JO", "2John", "2 João", "2Jo", ("2 Joao", "II João")),
    (64, "3JO", "3John", "3 João", "3Jo", ("3 Joao", "III João")),
    (65, "JUD", "Jude", "Judas", "Jd", ()),
    (66, "REV", "Rev", "Apocalipse", "Ap", ("Revelação", "Revelacao")),
]


def _group_for(ordinal: int) -> str:
    return next(name for rng, name in _GROUPS if ordinal in rng)


BOOKS: list[Book] = [
    Book(o, eb, osis, name, ab, "AT" if o <= 39 else "NT", _group_for(o), aliases)
    for o, eb, osis, name, ab, aliases in _RAW
]
BY_ORDINAL = {b.ordinal: b for b in BOOKS}
BY_EBIBLE = {b.ebible: b for b in BOOKS}
BY_OSIS = {b.osis: b for b in BOOKS}


def normalize(text: str) -> str:
    """Lowercase, strip accents and dots, collapse spaces, glue leading numerals ("1 jo" → "1jo")."""
    s = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    s = s.lower().replace(".", " ").strip()
    s = re.sub(r"^(iii|ii|i)\s+(?=[a-z])", lambda m: {"i": "1", "ii": "2", "iii": "3"}[m.group(1)], s)
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"^([123])\s+", r"\1", s)


def _build_lookup() -> dict[str, Book]:
    table: dict[str, Book] = {}
    for b in BOOKS:
        for key in (b.name, b.abbrev, b.osis, b.ebible, *b.aliases):
            table.setdefault(normalize(key), b)
    # Ambiguity: "jo" is João (John) in Portuguese convention; Job is "jó" → normalizes to "jo".
    table["jo"] = BY_ORDINAL[43]
    table["jó"] = BY_ORDINAL[18]
    return table


_LOOKUP = _build_lookup()


def find_book(name: str) -> Book | None:
    """Resolve a Portuguese/English book name or abbreviation (accent-insensitive)."""
    raw = name.strip()
    if raw.lower() in ("jó", "job"):
        return BY_ORDINAL[18]
    return _LOOKUP.get(normalize(raw))
