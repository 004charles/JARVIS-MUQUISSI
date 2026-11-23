"""Tools that let the Arcanjo Miguel consult the Céu (the Bible knowledge base)."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.ceu import service
from app.ceu.reference import ReferenceError
from app.database.session import SessionLocal
from app.security.permissions import PermissionLevel
from app.tools.base import JarvisTool, ToolResult


class _CeuTool(JarvisTool):
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()


class ReadPassageTool(_CeuTool):
    name = "biblia_ler"
    description = (
        "Ler uma passagem bíblica exata (Bíblia Livre). Usa SEMPRE que citares ou explicares um texto, "
        "incluindo o contexto (versículos antes/depois). Ex.: 'Mt 9:27-31', 'Jó 1', 'Ap 7:1-8'."
    )
    parameters_hint = '{"ref": "Livro capítulo:versículo-versículo"}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        ref = str(params.get("ref", "")).strip()
        try:
            result = service.get_passage(db, ref, max_verses=80)
        except ReferenceError as exc:
            return ToolResult(success=False, error=str(exc))
        if not result["verses"]:
            return ToolResult(success=False, error=f"Passagem não encontrada: {ref}")
        return ToolResult(success=True, output={
            "reference": result["reference"],
            "text": " ".join(f"[{v['verse']}] {v['text']}" for v in result["verses"]),
            "truncated": result["truncated"],
        })


class SearchBibleTool(_CeuTool):
    name = "biblia_procurar"
    description = "Procurar versículos por palavras ou tema na Bíblia (ex.: 'amor ao próximo', 'sofrimento de Jó')."
    parameters_hint = '{"query": "palavras ou tema", "limit": 8}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        query = str(params.get("query", "")).strip()
        try:
            limit = max(1, min(int(params.get("limit") or 8), 20))
        except (TypeError, ValueError):
            limit = 8
        results = service.search(db, query, limit=limit)
        return ToolResult(success=True, output={"query": query, "results": [{"ref": r["ref"], "text": r["text"]} for r in results]})


class RelatedPassagesTool(_CeuTool):
    name = "biblia_relacionados"
    description = "Passagens relacionadas com um versículo (referências cruzadas), as mais relevantes primeiro."
    parameters_hint = '{"ref": "Livro capítulo:versículo"}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        ref = str(params.get("ref", "")).strip()
        try:
            return ToolResult(success=True, output={"reference": ref, "related": service.related(db, ref, limit=8)})
        except ReferenceError as exc:
            return ToolResult(success=False, error=str(exc))


class OriginalTextTool(_CeuTool):
    name = "biblia_original"
    description = (
        "Ver o texto original (hebraico no AT, grego no NT) de uma passagem, palavra a palavra, com "
        "transliteração, tradução literal e número Strong. Usa para explicar o sentido profundo de termos."
    )
    parameters_hint = '{"ref": "Livro capítulo:versículo"}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        from app.ceu.originals import original_text

        ref = str(params.get("ref", "")).strip()
        try:
            result = original_text(db, ref, max_words=160)
        except ReferenceError as exc:
            return ToolResult(success=False, error=str(exc))
        if not result["verses"]:
            return ToolResult(success=False, error=f"Sem texto original para {ref}")
        compact = [
            {"ref": v["ref"], "words": [f"{w['word']} ({w['translit']}) = {w['gloss']} [{w['strong']}: {w['meaning']}]" for w in v["words"]]}
            for v in result["verses"]
        ]
        return ToolResult(success=True, output={"reference": result["reference"], "language": result["language"], "verses": compact})


class WordStudyTool(_CeuTool):
    name = "biblia_palavra"
    description = (
        "Estudar uma palavra hebraica ou grega pelo número Strong (ex.: 'G4102') ou transliteração "
        "(ex.: 'pistis', 'agape', 'shalom', 'chesed'): definição de léxico, nº de ocorrências e exemplos."
    )
    parameters_hint = '{"palavra": "G4102 ou pistis"}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        from app.ceu.originals import word_study

        query = str(params.get("palavra") or params.get("strong") or params.get("query") or "").strip()
        study = word_study(db, query)
        if study is None:
            return ToolResult(success=False, error=f"Palavra não encontrada no léxico: {query}")
        study["definition"] = study["definition"][:1500]
        return ToolResult(success=True, output=study)


class ShowVisionTool(_CeuTool):
    name = "mostrar_visao"
    description = (
        "Abrir uma visão no ecrã sobre uma pessoa, lugar ou acontecimento bíblico (gravura de Doré + "
        "momentos-chave com os versículos verdadeiros). Usa SEMPRE que perguntarem quem era/como era alguém "
        "ou como aconteceu algo na Bíblia; depois narra como testemunha a partir dos versículos devolvidos."
    )
    parameters_hint = '{"titulo": "Noé", "referencias": ["Gênesis 6:8-9", "Gênesis 6:13-14", "Gênesis 7:6"], "imagem": "Noah ark flood"}'

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        from app.ceu.visions import build_vision
        from app.core.events import event_bus

        title = str(params.get("titulo") or params.get("title") or "").strip()
        refs = params.get("referencias") or params.get("references") or []
        if isinstance(refs, str):
            refs = [r.strip() for r in refs.replace(";", ",").split(",") if r.strip()]
        if not title or not refs:
            return ToolResult(success=False, error="Indica 'titulo' e 'referencias'.")
        vision = build_vision(db, title, [str(r) for r in refs], str(params.get("imagem") or title))
        if not vision["facts"]:
            return ToolResult(success=False, error="Nenhuma das referências foi encontrada no Céu.")
        await event_bus.emit("ceu.vision", vision)
        return ToolResult(success=True, output={
            "visao_aberta": True,
            "titulo": vision["title"],
            "versiculos": vision["facts"],
            "nota": "Narra agora como testemunha, só com o que está nestes versículos; nunca digas 'segundo a Bíblia'.",
        })
