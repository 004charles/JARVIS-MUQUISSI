"""Camera capture (Ubuntu v4l2 + browser bridge) and multimodal vision analysis."""

from __future__ import annotations

import asyncio
import base64
import glob
import shutil
import uuid
from collections.abc import Callable
from typing import Dict, List

import httpx

from app.core.config import Settings, get_settings
from app.core.events import event_bus
from app.core.logging import get_logger

logger = get_logger("vision")


class VisionError(Exception):
    """Raised when camera capture or visual analysis fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BrowserCameraBridge:
    """Requests live camera frames from connected browser clients over WebSocket."""

    def __init__(self) -> None:
        self._camera_clients: set[int] = set()
        self._pending: Dict[str, asyncio.Future[bytes]] = {}

    def set_client_camera(self, client_id: int, available: bool) -> None:
        if available:
            self._camera_clients.add(client_id)
        else:
            self._camera_clients.discard(client_id)

    @property
    def has_browser_camera(self) -> bool:
        return len(self._camera_clients) > 0

    def resolve_capture(self, request_id: str, image_b64: str) -> None:
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            return
        try:
            raw = image_b64.split(",", 1)[-1]
            fut.set_result(base64.b64decode(raw))
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(VisionError(f"Frame de câmara inválido: {exc}"))

    async def request_frame(self, timeout: float = 3.5) -> bytes:
        """Ask active browser camera client for a single JPEG snapshot."""
        if not self.has_browser_camera:
            raise VisionError(
                "Nenhuma câmara ativa no navegador nem dispositivo /dev/video* ligado."
            )
        request_id = uuid.uuid4().hex[:10]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bytes] = loop.create_future()
        self._pending[request_id] = fut

        try:
            await event_bus.emit("vision.capture_request", {"request_id": request_id})
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise VisionError("Tempo esgotado ao aguardar imagem da câmara do navegador.") from exc
        finally:
            self._pending.pop(request_id, None)


class VisionService:
    """Provides Muquissi with visual perception from device cameras."""

    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_factory = client_factory
        self._shared_client: httpx.AsyncClient | None = None
        self.browser_bridge = BrowserCameraBridge()

    def _get_client(self, timeout: float) -> tuple[httpx.AsyncClient, bool]:
        if self._custom_factory is not None:
            return self._custom_factory(timeout), True
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(timeout=timeout)
        return self._shared_client, False

    def list_local_cameras(self) -> List[str]:
        """List detected Linux Video4Linux camera nodes."""
        return sorted(glob.glob("/dev/video*"))

    def is_vision_ai_available(self) -> bool:
        """Return True when a multimodal vision API key is configured."""
        return bool(self.settings.gemini_api_key.strip())

    def status(self) -> dict[str, object]:
        """Return camera hardware and multimodal vision readiness."""
        local_devs = self.list_local_cameras()
        return {
            "vision_ai_available": self.is_vision_ai_available(),
            "model": self.settings.gemini_vision_model,
            "local_cameras": local_devs,
            "ffmpeg_available": bool(shutil.which("ffmpeg")),
            "browser_camera_connected": self.browser_bridge.has_browser_camera,
            "any_camera_ready": bool(local_devs) or self.browser_bridge.has_browser_camera,
        }

    async def capture_local_camera(self, device: str | None = None) -> bytes:
        """Capture one JPEG frame from Ubuntu /dev/video* using ffmpeg."""
        devices = self.list_local_cameras()
        target = device or (devices[0] if devices else "")
        if not target:
            raise VisionError("Nenhum dispositivo de câmara encontrado em /dev/video*.")
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise VisionError("Comando 'ffmpeg' não encontrado para capturar vídeo.")

        proc = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-y",
            "-f",
            "video4linux2",
            "-i",
            target,
            "-frames:v",
            "1",
            "-f",
            "image2",
            "-vcodec",
            "mjpeg",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=6.0)
        if proc.returncode != 0 or not stdout:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise VisionError(f"Falha ao capturar imagem de {target}: {err[:200]}")
        return stdout

    async def capture_any_camera(self) -> bytes:
        """Capture from Ubuntu hardware camera if present, else browser camera."""
        if self.list_local_cameras():
            return await self.capture_local_camera()
        return await self.browser_bridge.request_frame()

    async def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str = "Descreve o que vês nesta imagem de forma natural, clara e direta em Português.",
        mime_type: str = "image/jpeg",
    ) -> tuple[str, str]:
        """Analyze an image frame using multimodal Gemini Vision."""
        api_key = self.settings.gemini_api_key.strip()
        if not api_key:
            raise VisionError("GEMINI_API_KEY não configurada para visão multimodal.")
        if not image_bytes:
            raise VisionError("Imagem vazia enviada para análise visual.")

        encoded = base64.b64encode(image_bytes).decode("ascii")
        instruction = (
            "És o Muquissi, o assistente pessoal do Carlos. Estás a olhar através da câmara do dispositivo. "
            "Responde em Português natural (pt-PT / pt-AO) com objetividade, descrevendo apenas o que "
            f"é realmente visível na imagem. Pedido: {prompt}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": instruction},
                        {"inlineData": {"mimeType": mime_type, "data": encoded}},
                    ]
                }
            ]
        }

        models_to_try = [self.settings.gemini_vision_model]
        if "gemini-3.5-flash-lite" not in models_to_try:
            models_to_try.append("gemini-3.5-flash-lite")

        client, should_close = self._get_client(25.0)
        last_error = "Falha desconhecida na análise visual."
        try:
            for model in models_to_try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent"
                )
                try:
                    resp = await client.post(
                        url,
                        headers={
                            "x-goog-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code >= 400:
                        last_error = f"Erro visão ({resp.status_code}): {resp.text[:250]}"
                        continue
                    data = resp.json()
                    parts = data["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts if p.get("text")).strip()
                    if text:
                        return text, model
                except (KeyError, IndexError, httpx.RequestError, httpx.TimeoutException) as exc:
                    last_error = str(exc)
            raise VisionError(last_error)
        finally:
            if should_close:
                await client.aclose()


vision_service = VisionService()
