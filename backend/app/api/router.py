"""Versioned API router."""

from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.ai import router as ai_router
from app.api.conversations import router as conversations_router
from app.api.desktop import router as desktop_router
from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.notifications import router as notifications_router
from app.api.productivity import router as productivity_router
from app.api.projects import router as projects_router
from app.api.system import router as system_router
from app.api.tools import router as tools_router
from app.api.vision import router as vision_router
from app.api.voice import router as voice_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(system_router)
api_router.include_router(conversations_router)
api_router.include_router(ai_router)
api_router.include_router(voice_router)
api_router.include_router(tools_router)
api_router.include_router(notifications_router)
api_router.include_router(memory_router)
api_router.include_router(projects_router)
api_router.include_router(productivity_router)
api_router.include_router(vision_router)
api_router.include_router(agents_router)
api_router.include_router(desktop_router)
