"""Tasks, agenda reminders, notes, and safe web search endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.web_research import search_web
from app.database.models import AgendaEvent, NoteItem, TaskItem
from app.database.session import get_db

router = APIRouter(tags=["productivity"])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    project_id: int | None = None


class TaskUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|in_progress|done)$")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    priority: str | None = Field(default=None, pattern="^(low|medium|high)$")


class AgendaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    start_at: datetime | None = None


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=4000)
    project_id: int | None = None


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = list(db.scalars(select(TaskItem).order_by(TaskItem.id.desc())).all())
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "project_id": t.project_id,
            "created_at": t.created_at.isoformat(),
        }
        for t in rows
    ]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    task = TaskItem(
        title=payload.title.strip(),
        description=payload.description.strip(),
        priority=payload.priority,
        project_id=payload.project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "project_id": task.project_id,
        "created_at": task.created_at.isoformat(),
    }


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)
) -> dict[str, object]:
    task = db.get(TaskItem, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarefa não encontrada.")
    if payload.status is not None:
        task.status = payload.status
    if payload.title is not None:
        task.title = payload.title.strip()
    if payload.priority is not None:
        task.priority = payload.priority
    db.commit()
    db.refresh(task)
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    task = db.get(TaskItem, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarefa não encontrada.")
    db.delete(task)
    db.commit()
    return {"deleted": True, "id": task_id}


@router.get("/agenda")
def list_agenda(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = list(db.scalars(select(AgendaEvent).order_by(AgendaEvent.start_at.asc())).all())
    return [
        {
            "id": ev.id,
            "title": ev.title,
            "description": ev.description,
            "start_at": ev.start_at.isoformat(),
            "reminder_sent": ev.reminder_sent,
        }
        for ev in rows
    ]


@router.post("/agenda", status_code=status.HTTP_201_CREATED)
def create_agenda_event(payload: AgendaCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    ev = AgendaEvent(
        title=payload.title.strip(),
        description=payload.description.strip(),
        start_at=payload.start_at or datetime.now(timezone.utc),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {
        "id": ev.id,
        "title": ev.title,
        "description": ev.description,
        "start_at": ev.start_at.isoformat(),
    }


@router.delete("/agenda/{event_id}")
def delete_agenda_event(event_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    ev = db.get(AgendaEvent, event_id)
    if ev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento não encontrado.")
    db.delete(ev)
    db.commit()
    return {"deleted": True, "id": event_id}


@router.get("/notes")
def list_notes(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = list(db.scalars(select(NoteItem).order_by(NoteItem.updated_at.desc())).all())
    return [
        {
            "id": n.id,
            "title": n.title,
            "content": n.content,
            "project_id": n.project_id,
            "updated_at": n.updated_at.isoformat(),
        }
        for n in rows
    ]


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    note = NoteItem(
        title=payload.title.strip(),
        content=payload.content.strip(),
        project_id=payload.project_id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "project_id": note.project_id,
        "updated_at": note.updated_at.isoformat(),
    }


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    note = db.get(NoteItem, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota não encontrada.")
    db.delete(note)
    db.commit()
    return {"deleted": True, "id": note_id}


@router.get("/web/search")
async def web_search_endpoint(q: str = Query(min_length=1, max_length=200)) -> dict[str, object]:
    """Perform a safe read-only web search."""
    try:
        results = await search_web(q, limit=6)
        return {"query": q, "results": results}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha na pesquisa Web: {exc}",
        ) from exc
