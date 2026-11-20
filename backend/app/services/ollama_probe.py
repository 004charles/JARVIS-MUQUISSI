"""Lightweight service probes for local dependencies such as Ollama."""

from __future__ import annotations

import httpx


async def check_ollama_status(base_url: str, timeout: float = 1.5) -> dict[str, object]:
    """Check whether a local Ollama server is reachable without failing the API."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return {"available": True, "models": models}
            return {"available": False, "models": [], "status_code": response.status_code}
    except Exception:  # noqa: BLE001
        return {"available": False, "models": []}
