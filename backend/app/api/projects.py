"""Project management and non-destructive project analysis endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.project_analyzer import analyze_project_directory
from app.database.models import ProjectEntry
from app.database.session import get_db
from app.security.permissions import SecurityPolicy, SecurityViolation, security_policy

router = APIRouter(prefix="/projects", tags=["projects"])


def get_security_policy() -> SecurityPolicy:
    """Dependency returning the active SecurityPolicy."""
    return security_policy


class ProjectCreateRequest(BaseModel):
    """Register an authorized local project."""

    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=1000)
    directory: str = Field(min_length=1, max_length=500)
    technologies: str = Field(default="", max_length=300)


def _serialize_project(p: ProjectEntry) -> dict[str, object]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "directory": p.directory,
        "technologies": p.technologies,
        "status": p.status,
        "git_repo": p.git_repo,
        "last_activity_at": p.last_activity_at.isoformat(),
        "created_at": p.created_at.isoformat(),
    }


@router.get("")
def list_projects(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """List registered projects."""
    rows = list(db.scalars(select(ProjectEntry).order_by(ProjectEntry.last_activity_at.desc())).all())
    return [_serialize_project(p) for p in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    policy: SecurityPolicy = Depends(get_security_policy),
) -> dict[str, object]:
    """Register a project after verifying its directory is authorized."""
    try:
        resolved = policy.validate_authorized_path(payload.directory)
    except SecurityViolation as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.reason) from exc

    if not resolved.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O caminho indicado não é um diretório.",
        )

    existing = db.scalar(select(ProjectEntry).where(ProjectEntry.name == payload.name.strip()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um projeto com esse nome.",
        )

    entry = ProjectEntry(
        name=payload.name.strip(),
        description=payload.description.strip(),
        directory=str(resolved),
        technologies=payload.technologies.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialize_project(entry)


@router.post("/{project_id}/analyze")
async def analyze_project(
    project_id: int,
    db: Session = Depends(get_db),
    policy: SecurityPolicy = Depends(get_security_policy),
) -> dict[str, object]:
    """Run non-destructive analysis on an authorized project directory."""
    entry = db.get(ProjectEntry, project_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")

    try:
        report = await analyze_project_directory(entry.directory, policy)
    except (SecurityViolation, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if report.get("technologies"):
        entry.technologies = ", ".join(report["technologies"])
    entry.last_activity_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)

    return {"project": _serialize_project(entry), "report": report}


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Remove project metadata entry (never touches files on disk)."""
    entry = db.get(ProjectEntry, project_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": project_id}
