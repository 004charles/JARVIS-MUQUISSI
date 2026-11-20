"""Camera vision status and multimodal image analysis endpoints."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.vision.service import VisionError, VisionService, vision_service

router = APIRouter(prefix="/vision", tags=["vision"])


def get_vision_service() -> VisionService:
    """Dependency returning the active VisionService."""
    return vision_service


class AnalyzeBase64Request(BaseModel):
    """Analyze a base64 camera snapshot or trigger active device camera capture."""

    prompt: str = Field(
        default="Descreve o que vês na câmara neste momento em Português.",
        max_length=1000,
    )
    image_b64: str | None = None
    mime_type: str = "image/jpeg"


@router.get("/status")
def read_vision_status(
    svc: VisionService = Depends(get_vision_service),
) -> dict[str, object]:
    """Return local/browser camera availability and vision model status."""
    return svc.status()


@router.post("/analyze")
async def analyze_camera_frame(
    payload: AnalyzeBase64Request,
    svc: VisionService = Depends(get_vision_service),
) -> dict[str, str]:
    """Analyze a supplied base64 camera frame or capture directly from active camera."""
    try:
        if payload.image_b64:
            raw = payload.image_b64.split(",", 1)[-1]
            image_bytes = base64.b64decode(raw)
        else:
            image_bytes = await svc.capture_any_camera()

        description, model = await svc.analyze_image(
            image_bytes=image_bytes,
            prompt=payload.prompt,
            mime_type=payload.mime_type,
        )
        return {"description": description, "model": model}
    except VisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Imagem inválida: {exc}",
        ) from exc


@router.post("/analyze-upload")
async def analyze_uploaded_image(
    image: UploadFile = File(...),
    prompt: str = Form("Descreve esta imagem em Português."),
    svc: VisionService = Depends(get_vision_service),
) -> dict[str, str]:
    """Analyze a multipart uploaded image file."""
    raw_bytes = await image.read()
    try:
        description, model = await svc.analyze_image(
            image_bytes=raw_bytes,
            prompt=prompt,
            mime_type=image.content_type or "image/jpeg",
        )
        return {"description": description, "model": model}
    except VisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
