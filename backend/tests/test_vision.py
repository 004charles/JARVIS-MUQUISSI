"""Tests for Muquissi device camera vision service, bridge, tool, and endpoints."""

from __future__ import annotations

import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import vision as vision_api
from app.core.config import Settings
from app.vision.service import BrowserCameraBridge, VisionError, VisionService

_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


@pytest.mark.asyncio
async def test_vision_service_analyzes_image_with_fallback() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["x-goog-api-key"] == "AQ.test-vision"
        if "gemini-3.5-flash:" in request.url.path:
            return httpx.Response(503, text="busy")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Vejo uma secretária iluminada."}]}}
                ]
            },
        )

    svc = VisionService(
        settings=Settings(gemini_api_key="AQ.test-vision", gemini_vision_model="gemini-3.5-flash"),
        client_factory=lambda t: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=t
        ),
    )

    description, model = await svc.analyze_image(
        image_bytes=base64.b64decode(_TINY_PNG_B64),
        prompt="O que vês?",
        mime_type="image/png",
    )
    assert description == "Vejo uma secretária iluminada."
    assert model == "gemini-3.5-flash-lite"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_vision_service_errors_honestly_without_camera_or_key() -> None:
    svc = VisionService(settings=Settings(gemini_api_key=""))
    with pytest.raises(VisionError):
        await svc.analyze_image(b"abc")

    bridge = BrowserCameraBridge()
    assert bridge.has_browser_camera is False
    with pytest.raises(VisionError):
        await bridge.request_frame(timeout=0.1)


def test_vision_rest_endpoints_status_and_analyze_base64(client: TestClient) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Um teclado mecânico."}]}}
                ]
            },
        )

    mock_svc = VisionService(
        settings=Settings(gemini_api_key="AQ.test-ep"),
        client_factory=lambda t: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=t
        ),
    )
    client.app.dependency_overrides[vision_api.get_vision_service] = lambda: mock_svc

    status_resp = client.get("/api/v1/vision/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["vision_ai_available"] is True

    analyze_resp = client.post(
        "/api/v1/vision/analyze",
        json={
            "prompt": "O que é isto?",
            "image_b64": f"data:image/png;base64,{_TINY_PNG_B64}",
            "mime_type": "image/png",
        },
    )
    assert analyze_resp.status_code == 200
    assert analyze_resp.json()["description"] == "Um teclado mecânico."


def test_websocket_vision_register_and_capture_bridge(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()  # connection.ready
        websocket.send_json({"type": "vision.register", "available": True})
        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
