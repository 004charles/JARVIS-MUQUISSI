"""O Céu — public Bible API (passages, search, related passages, books)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.ceu import service
from app.ceu.reference import ReferenceError
from app.database.session import get_db

router = APIRouter(prefix="/ceu", tags=["ceu"])


@router.get("/books")
def books(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"books": service.list_books(db), "attribution": service.attribution(db)}


@router.get("/passage")
def passage(ref: str = Query(..., min_length=2, max_length=120), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        result = service.get_passage(db, ref)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result["verses"]:
        raise HTTPException(status_code=404, detail=f"Passagem não encontrada: {ref}")
    return result


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=200), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"query": q, "results": service.search(db, q, limit=limit), "attribution": service.attribution(db)}


@router.get("/related")
def related(ref: str = Query(..., min_length=2, max_length=120), limit: int = Query(8, ge=1, le=30), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"reference": ref, "related": service.related(db, ref, limit=limit)}
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/original")
def original(ref: str = Query(..., min_length=2, max_length=120), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.ceu.originals import original_text

    try:
        result = original_text(db, ref)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result["verses"]:
        raise HTTPException(status_code=404, detail=f"Sem texto original para {ref}")
    return result


@router.get("/word")
def word(q: str = Query(..., min_length=2, max_length=60), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.ceu.originals import word_study

    study = word_study(db, q)
    if study is None:
        raise HTTPException(status_code=404, detail=f"Palavra não encontrada: {q}")
    return study


@router.get("/daily")
def daily(day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), db: Session = Depends(get_db)) -> dict[str, Any]:
    """A Palavra do dia (one verse per day, proclaimed by the Arcanjo)."""
    from datetime import date as _date

    from app.ceu.daily import daily_word

    return daily_word(db, _date.fromisoformat(day) if day else None)
