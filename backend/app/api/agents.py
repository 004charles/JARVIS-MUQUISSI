"""Phase 9 specialized agents listing, execution, and mission history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents import agent_orchestrator
from app.database.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentMissionRequest(BaseModel):
    """Payload to launch a specialized multi-step agent mission."""

    goal: str = Field(min_length=2, max_length=2000)
    agent_type: str | None = Field(default=None, max_length=40)
    max_steps: int = Field(default=4, ge=1, le=6)


@router.get("")
async def list_agents() -> dict[str, object]:
    """List the 5 specialized Arcanjo agents and their authorized tool scopes."""
    return {"agents": agent_orchestrator.list_profiles()}


@router.get("/runs")
async def list_agent_runs(
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """List recent persisted agent missions."""
    return {"runs": agent_orchestrator.list_runs(db, limit=limit)}


@router.post("/run")
async def run_agent_mission(
    payload: AgentMissionRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Execute a specialized multi-step agent mission under permission levels 1-3."""
    try:
        result = await agent_orchestrator.run_mission(
            db=db,
            goal=payload.goal,
            agent_type=payload.agent_type,
            max_steps=payload.max_steps,
        )
        return result.to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
