"""Camera vision tool allowing Muquissi to look through the device camera."""

from __future__ import annotations

from typing import Any, Dict

from app.security.permissions import PermissionLevel
from app.tools.base import JarvisTool, ToolResult
from app.vision.service import VisionError, vision_service


class LookCameraTool(JarvisTool):
    """Capture a frame from the device camera and analyze what is visible."""

    name = "look_camera"
    description = (
        "Olhar pela câmara do dispositivo (webcam Ubuntu ou câmara do browser ativa) "
        "e responder ao que está visível."
    )
    parameters_hint = '{"question": "o-que-analisar-na-imagem"}'
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        question = str(
            params.get("question")
            or "Descreve claramente o que vês na câmara neste momento."
        ).strip()
        try:
            frame_bytes = await vision_service.capture_any_camera()
            description, model = await vision_service.analyze_image(
                image_bytes=frame_bytes,
                prompt=question,
                mime_type="image/jpeg",
            )
            return ToolResult(
                success=True,
                output={"description": description, "model": model},
            )
        except VisionError as exc:
            return ToolResult(success=False, error=exc.message)
