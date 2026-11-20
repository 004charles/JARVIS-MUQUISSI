"""Local Ollama AI provider with availability checks and NDJSON streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Sequence

import httpx

from app.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderStatus


class OllamaProvider(AIProvider):
    """Connects to a local Ollama server over HTTP."""

    name = "ollama"
    kind = "local"

    def __init__(
        self,
        base_url: str,
        default_model: str,
        timeout: int = 60,
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._client_factory = client_factory or (
            lambda t: httpx.AsyncClient(timeout=t)
        )

    async def status(self) -> ProviderStatus:
        """Query Ollama `/api/tags` to verify availability and installed models."""
        try:
            async with self._client_factory(2.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return ProviderStatus(
                        name=self.name,
                        kind=self.kind,
                        available=False,
                        configured=True,
                        default_model=self.default_model,
                        detail=f"Ollama respondeu com HTTP {response.status_code}.",
                    )
                payload = response.json()
                models = [
                    m["name"] for m in payload.get("models", []) if m.get("name")
                ]
                return ProviderStatus(
                    name=self.name,
                    kind=self.kind,
                    available=True,
                    configured=True,
                    default_model=self.default_model,
                    models=models,
                    detail="Servidor Ollama operacional.",
                )
        except Exception as exc:  # noqa: BLE001
            return ProviderStatus(
                name=self.name,
                kind=self.kind,
                available=False,
                configured=True,
                default_model=self.default_model,
                detail=f"Ollama indisponível em {self.base_url}: {exc}",
            )

    def _build_payload(
        self, messages: Sequence[ChatMessage], model: str | None, stream: bool
    ) -> dict[str, object]:
        return {
            "model": model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }

    async def generate(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> str:
        """Generate a single non-streaming completion via Ollama `/api/chat`."""
        payload = self._build_payload(messages, model, stream=False)
        try:
            async with self._client_factory(float(self.timeout)) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                if response.status_code >= 400:
                    raise AIProviderError(
                        self.name,
                        f"Erro Ollama ({response.status_code}): {response.text}",
                    )
                data = response.json()
                content = data.get("message", {}).get("content", "")
                if not content:
                    raise AIProviderError(self.name, "Ollama devolveu uma resposta vazia.")
                return str(content)
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                self.name, f"Tempo limite excedido ao contactar Ollama ({self.timeout}s)."
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(
                self.name,
                f"Não foi possível ligar ao Ollama em {self.base_url}. Verifica se o serviço está ativo.",
            ) from exc

    async def stream(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream response tokens line-by-line from Ollama `/api/chat`."""
        payload = self._build_payload(messages, model, stream=True)
        try:
            async with self._client_factory(float(self.timeout)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise AIProviderError(
                            self.name,
                            f"Erro Ollama ({response.status_code}): {body}",
                        )
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            raise AIProviderError(self.name, str(chunk["error"]))
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            yield str(delta)
                        if chunk.get("done"):
                            break
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                self.name, f"Tempo limite excedido durante streaming Ollama ({self.timeout}s)."
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(
                self.name,
                f"Não foi possível ligar ao Ollama em {self.base_url}. Verifica se o serviço está ativo.",
            ) from exc
