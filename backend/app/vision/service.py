"""Camera capture (Ubuntu v4l2 + browser bridge) and multimodal vision analysis."""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import re
import shutil
import tempfile
import uuid
from pathlib import Path
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
    """Provides Arcanjo with visual perception from device cameras."""

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
        return bool(self.settings.gemini_api_key.strip() or self.settings.groq_api_key.strip())

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
            if shutil.which("gst-launch-1.0"):
                return await self._capture_with_gstreamer(target)
            raise VisionError("Nem 'ffmpeg' nem GStreamer encontrados para capturar vídeo.")

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

    async def _capture_with_gstreamer(self, device: str) -> bytes:
        """Grab a few frames (auto-exposure warm-up) and keep the last one as JPEG."""
        with tempfile.TemporaryDirectory(prefix="muquissi-cam-") as tmp:
            proc = await asyncio.create_subprocess_exec(
                "gst-launch-1.0",
                "-q",
                "v4l2src",
                f"device={device}",
                "num-buffers=12",
                "!",
                "videoconvert",
                "!",
                "jpegenc",
                "quality=85",
                "!",
                "multifilesink",
                f"location={tmp}/f%02d.jpg",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError as exc:
                proc.kill()
                raise VisionError("A câmara não respondeu a tempo.") from exc
            frames = sorted(Path(tmp).glob("f*.jpg"))
            if not frames:
                err = stderr.decode("utf-8", errors="replace").strip()
                raise VisionError(f"Falha ao capturar imagem de {device}: {err[:200]}")
            return frames[-1].read_bytes()

    async def capture_frame_and_thumbnail(self) -> tuple[bytes, bytes]:
        """One camera grab → (JPEG, 64x48 grayscale thumbnail) for cheap change detection."""
        devices = self.list_local_cameras()
        if not devices or not shutil.which("gst-launch-1.0"):
            frame = await self.capture_any_camera()
            return frame, b""
        with tempfile.TemporaryDirectory(prefix="muquissi-eye-") as tmp:
            proc = await asyncio.create_subprocess_exec(
                "gst-launch-1.0", "-q",
                "v4l2src", f"device={devices[0]}", "num-buffers=10", "!",
                "videoconvert", "!", "tee", "name=t",
                "t.", "!", "queue", "!", "jpegenc", "quality=80", "!",
                "multifilesink", f"location={tmp}/f%02d.jpg",
                "t.", "!", "queue", "!", "videoscale", "!", "videoconvert", "!",
                "video/x-raw,format=GRAY8,width=64,height=48", "!",
                "multifilesink", f"location={tmp}/g%02d.raw",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError as exc:
                proc.kill()
                raise VisionError("A câmara não respondeu a tempo.") from exc
            frames = sorted(Path(tmp).glob("f*.jpg"))
            thumbs = sorted(Path(tmp).glob("g*.raw"))
            if not frames:
                err = stderr.decode("utf-8", errors="replace").strip()
                raise VisionError(f"Falha ao capturar imagem: {err[:200]}")
            return frames[-1].read_bytes(), (thumbs[-1].read_bytes() if thumbs else b"")

    async def describe_scene(self, image_bytes: bytes) -> dict[str, object]:
        """Understand the camera frame as structured perception (person, clothes, activity, mood)."""
        prompt = (
            "És os olhos do Arcanjo, a IA do Carlos; esta imagem é da webcam do portátil dele. "
            "Responde SÓ com JSON: {\"pessoa\": true/false, \"roupa\": \"cor e tipo da roupa visível\", "
            "\"atividade\": \"o que a pessoa está a fazer (ex.: a programar, a comer, ao telemóvel, a falar com alguém, "
            "a espreguiçar-se)\", \"expressao\": \"estado aparente (concentrado, cansado, sorridente...)\", "
            "\"descricao\": \"1 frase natural com o essencial, incluindo detalhes do ambiente (luz, objetos)\"}. "
            "\"texto_mostrado\": true/false (true se alguém mostra à câmara um papel, cartaz ou ecrã "
            "com texto escrito). NUNCA transcrevas texto que apareça na imagem. "
            "Descreve só o que é visível, sem inventar."
        )
        text, _model = await self.analyze_image(image_bytes=image_bytes, prompt=prompt)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
        return {"pessoa": True, "descricao": text.strip()[:300]}

    async def _analyze_with_groq(self, image_bytes: bytes, instruction: str, mime_type: str) -> tuple[str, str]:
        model = self.settings.groq_vision_model
        encoded = base64.b64encode(image_bytes).decode("ascii")
        client, should_close = self._get_client(30.0)
        try:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.groq_api_key.strip()}"},
                json={
                    "model": model,
                    "max_tokens": 400,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": instruction},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                                },
                            ],
                        }
                    ],
                },
            )
            if resp.status_code >= 400:
                raise VisionError(f"Erro visão Groq ({resp.status_code}): {resp.text[:250]}")
            choices = resp.json().get("choices") or []
            text = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
            if not text:
                raise VisionError("A visão Groq devolveu resposta vazia.")
            return text, model
        except httpx.RequestError as exc:
            raise VisionError(f"Falha de rede na visão Groq: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

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
        if not image_bytes:
            raise VisionError("Imagem vazia enviada para análise visual.")

        encoded = base64.b64encode(image_bytes).decode("ascii")
        instruction = (
            "És o Arcanjo, o assistente pessoal do Carlos. Estás a olhar através da câmara do dispositivo. "
            "Responde em Português natural (pt-PT / pt-AO) com objetividade, descrevendo apenas o que "
            f"é realmente visível na imagem. Pedido: {prompt}"
        )
        if not api_key:
            if self.settings.groq_api_key.strip():
                return await self._analyze_with_groq(image_bytes, instruction, mime_type)
            raise VisionError("Configura GROQ_API_KEY ou GEMINI_API_KEY para a visão funcionar.")
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
