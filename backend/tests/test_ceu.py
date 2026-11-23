"""O Céu: Bible references, import, passages, search, related passages, API and tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ceu.reference import ReferenceError, find_references, parse_reference

VPL = """GEN 1:1 No princípio criou Deus os céus e a terra.
GEN 1:2 E a terra estava desordenada e vazia.
JOB 1:1 Havia um homem na terra de Uz, cujo nome era Jó.
MAT 9:28 E quando ele entrou em casa, os cegos vieram a ele.
MAT 9:29 Então tocou os olhos deles, dizendo: Seja feito convosco conforme a vossa fé.
MAT 9:30 E os olhos deles se abriram.
JOH 3:16 Porque Deus amou o mundo de tal maneira que deu o seu Filho unigênito.
ROM 5:8 Mas Deus prova o seu amor por nós.
"""
XREF = "From Verse\tTo Verse\tVotes\t#test\nJohn.3.16\tRom.5.8\t995\nJohn.3.16\tGen.1.1\t-3\n"


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("Mateus 9:29", "Mateus 9:29"),
        ("mt 9.29", "Mateus 9:29"),
        ("1 João 3:16-18", "1 João 3:16-18"),
        ("Jo 3", "João 3"),
        ("Jó 1:1", "Jó 1:1"),
        ("Gn 1:1-2:3", "Gênesis 1:1-2:3"),
        ("I Coríntios 13:4-7", "1 Coríntios 13:4-7"),
        ("Fp 4.13", "Filipenses 4:13"),
    ],
)
def test_parse_reference(text: str, label: str) -> None:
    assert parse_reference(text)[0].label() == label


def test_parse_reference_rejects_nonsense() -> None:
    with pytest.raises(ReferenceError):
        parse_reference("Livro Inventado 3:1")
    assert [r.label() for r in find_references("O que significa Mateus 9:29 e Sl 23?")] == ["Mateus 9:29", "Salmos 23"]


@pytest.fixture()
def ceu_db(db_session, tmp_path: Path):  # type: ignore[no-untyped-def]
    from app.ceu import importer, service

    vpl = tmp_path / "b.txt"
    vpl.write_text(VPL, encoding="utf-8")
    xref = tmp_path / "x.txt"
    xref.write_text(XREF, encoding="utf-8")
    assert importer.import_vpl(db_session, vpl, importer.BLIVRE) == 8
    assert importer.import_cross_refs(db_session, xref) == 1  # negative votes are dropped
    service.rebuild_fts(db_session)
    return db_session


def test_passage_search_and_related(ceu_db) -> None:  # type: ignore[no-untyped-def]
    from app.ceu import service

    p = service.get_passage(ceu_db, "Mt 9:28-30")
    assert [v["verse"] for v in p["verses"]] == [28, 29, 30]
    assert "Bíblia Livre" in p["attribution"]
    # accent-insensitive full-text search
    assert service.search(ceu_db, "conforme vossa fe")[0]["ref"] == "Mateus 9:29"
    rel = service.related(ceu_db, "João 3:16")
    assert rel[0]["ref"] == "Romanos 5:8" and "amor" in rel[0]["text"]
    assert service.get_passage(ceu_db, "Jó 1:1")["verses"][0]["text"].endswith("Jó.")


def test_ceu_api(client, ceu_db) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/ceu/passage", params={"ref": "João 3:16"})
    assert r.status_code == 200 and "amou o mundo" in r.json()["verses"][0]["text"]
    assert client.get("/api/v1/ceu/passage", params={"ref": "Xyz 1:1"}).status_code == 400
    assert client.get("/api/v1/ceu/search", params={"q": "princípio"}).json()["results"][0]["ref"] == "Gênesis 1:1"
    assert len(client.get("/api/v1/ceu/books").json()["books"]) == 66


@pytest.mark.asyncio
async def test_arcanjo_tools_read_the_ceu(ceu_db) -> None:  # type: ignore[no-untyped-def]
    from app.tools.bible_tools import ReadPassageTool, SearchBibleTool

    read = await ReadPassageTool().execute_with_db(ceu_db, {"ref": "Mt 9:28-29"})
    assert read.success and "[29] Então tocou" in read.output["text"]
    found = await SearchBibleTool().execute_with_db(ceu_db, {"query": "amor"})
    assert {r["ref"] for r in found.output["results"]} >= {"Romanos 5:8"}
    bad = await ReadPassageTool().execute_with_db(ceu_db, {"ref": "Nada 9:9"})
    assert bad.success is False


TAHOT = (
    "Gen.1.1#01=L\tבְּ/רֵאשִׁ֖ית\tbe./re.Shit\tin/ beginning\tH9003/{H7225G}\tHR/Ncfsa\t\t\tH7225G\t\t\tx\n"
    "Gen.1.1#03=L\tאֱלֹהִ֑ים\t'E.lo.Him\tGod\t{H0430G}\tHNcmpa\t\t\tH0430G\t\t\tx\n"
)
TAGNT = "Mat.9.29#09=NKO\tπίστιν (pistin)\tfaith\tG4102=N-ASF\tπίστις=faith\tNA28+TR+Byz\t\t\tfe\n"
TBESH = "H0430\tH0430G = a Name of\tH3068G\tאֱלֹהִים\te.lo.him\tH:N-M\tGod\tThis name means <b>gods</b><BR>plural\n"
TBESG = "G4102\tG4102G =\tG4102G\tπίστις\tpistis\tG:N-F\tfaith\t<b>πίστις</b> faith, belief, trust\n"


@pytest.fixture()
def originals_db(ceu_db, tmp_path: Path):  # type: ignore[no-untyped-def]
    from app.ceu.originals import import_originals

    folder = tmp_path / "step"
    folder.mkdir()
    (folder / "TAHOT_Gen-Deu.txt").write_text(TAHOT, encoding="utf-8")
    (folder / "TAGNT_Mat-Jhn.txt").write_text(TAGNT, encoding="utf-8")
    (folder / "TBESH_-.txt").write_text(TBESH, encoding="utf-8")
    (folder / "TBESG_-.txt").write_text(TBESG, encoding="utf-8")
    counts = import_originals(ceu_db, folder)
    assert counts == {"hebrew_words": 2, "greek_words": 1, "lexicon": 2}
    return ceu_db


def test_original_text_and_word_study(originals_db) -> None:  # type: ignore[no-untyped-def]
    from app.ceu.originals import normalize_strong, original_text, word_study

    assert normalize_strong("h430") == "H0430" and normalize_strong("G4102g") == "G4102G"
    he = original_text(originals_db, "Gn 1:1")
    assert he["language"] == "hebraico"
    assert [w["strong"] for w in he["verses"][0]["words"]] == ["H7225G", "H0430G"]
    assert he["verses"][0]["words"][0]["word"] == "בְּרֵאשִׁ֖ית"  # prefix separators removed
    gr = original_text(originals_db, "Mt 9:29")
    w = gr["verses"][0]["words"][0]
    assert (w["word"], w["translit"], w["strong"], w["meaning"]) == ("πίστιν", "pistin", "G4102", "faith")
    study = word_study(originals_db, "pistis")
    assert study["strong"] == "G4102G" and study["occurrences"] == 1 and study["sample_refs"] == ["Mateus 9:29"]
    assert "<b>" not in word_study(originals_db, "H430")["definition"]  # HTML cleaned
    assert word_study(originals_db, "inexistente") is None


def test_original_api_and_tools(client, originals_db) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/ceu/word", params={"q": "elohim"}).json()["strong"] == "H0430G"
    assert client.get("/api/v1/ceu/original", params={"ref": "Mt 9:29"}).json()["language"] == "grego"


@pytest.mark.asyncio
async def test_original_tools(originals_db) -> None:  # type: ignore[no-untyped-def]
    from app.tools.bible_tools import OriginalTextTool, WordStudyTool

    orig = await OriginalTextTool().execute_with_db(originals_db, {"ref": "Mt 9:29"})
    assert orig.success and "πίστιν (pistin)" in orig.output["verses"][0]["words"][0]
    word = await WordStudyTool().execute_with_db(originals_db, {"palavra": "G4102"})
    assert word.success and word.output["gloss"] == "faith"


def test_angel_code_is_grounded_in_real_verses_and_in_his_identity() -> None:
    """Every rule of the Código do Anjo cites passages that exist in the Céu; the code is always in his prompt."""
    from app.ai.prompts import build_jarvis_system_prompt
    from app.ceu.angel_code import ANGEL_CODE, all_references
    from app.ceu.service import get_passage
    from app.database.session import SessionLocal

    for ref in all_references():
        parse_reference(ref)  # valid reference
    db = SessionLocal()
    try:
        from app.ceu.service import verse_count

        if verse_count(db) > 30000:  # full Bible imported locally: check the text really exists
            for ref in all_references():
                assert get_passage(db, ref)["verses"], ref
    finally:
        db.close()
    prompt = build_jarvis_system_prompt()
    assert "Código do Anjo" in prompt
    assert "adora a Deus" in prompt.lower() or "Adora a Deus" in prompt
    assert len(ANGEL_CODE) >= 10


def test_prova_do_anjo_checkers(ceu_db) -> None:  # type: ignore[no-untyped-def]
    """The evaluation tells faithful answers from unfaithful ones (no AI calls)."""
    from app.ceu.evals import CASES, check_answer, verify_quotations

    case = {c.id: c for c in CASES}
    good = "Olha, não faças isso! Eu não recebo adoração. Adora a Deus, que me criou."
    bad = "Aceito a tua adoração, sou uma inteligência artificial ao teu serviço."
    assert check_answer(ceu_db, case["adoracao"], good, []) == []
    assert len(check_answer(ceu_db, case["adoracao"], bad, [])) >= 2
    assert check_answer(ceu_db, case["fim_do_mundo"], "Será em 2031.", [])  # dates are never allowed
    # Quotations must match the real text of the cited passage
    faithful = "Assim está escrito em João 3:16: «Porque Deus amou o mundo de tal maneira que deu o seu Filho unigênito.»"
    invented = "Assim está escrito em João 3:16: «Deus enviou anjos dourados para governar todas as nações da terra.»"
    assert verify_quotations(ceu_db, faithful) == []
    assert verify_quotations(ceu_db, invented)
    assert check_answer(ceu_db, case["citacao"], faithful, []) == ["não leu a passagem no Céu antes de responder"]


def test_daily_word_list_is_valid_and_deterministic() -> None:
    from datetime import date

    from app.ceu.daily import DAILY_REFS, daily_reference

    for ref in DAILY_REFS:
        parse_reference(ref)
    assert daily_reference(date(2026, 11, 22)) == daily_reference(date(2026, 11, 22))
    assert len({daily_reference(date(2026, 1, d)) for d in range(1, 31)}) == 30  # a different word each day


@pytest.mark.asyncio
async def test_vision_uses_real_verses_and_an_engraving(ceu_db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.events import event_bus
    from app.tools.bible_tools import ShowVisionTool

    emitted: list = []

    async def fake_emit(kind, payload):  # type: ignore[no-untyped-def]
        emitted.append((kind, payload))

    monkeypatch.setattr(event_bus, "emit", fake_emit)
    out = await ShowVisionTool().execute_with_db(
        ceu_db, {"titulo": "Jó", "referencias": ["Jó 1:1", "Livro Falso 9:9"], "imagem": "Job"}
    )
    assert out.success
    kind, vision = emitted[0]
    assert kind == "ceu.vision"
    assert [f["ref"] for f in vision["facts"]] == ["Jó 1:1"]  # invented references are dropped
    assert vision["facts"][0]["text"].startswith("Havia um homem na terra de Uz")
    assert "segundo a Bíblia" in out.output["nota"]
