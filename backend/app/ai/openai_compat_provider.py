"""Shared OpenAI-compatible provider supporting OpenAI and Groq endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import List, Sequence

import httpx

from app.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderStatus


class OpenAICompatProvider(AIProvider):
    """Unified provider for OpenAI and Groq chat completions APIs."""

    kind = "external"

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        suggested_models: List[str],
        timeout: int = 60,
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.default_model = default_model
        self.suggested_models = suggested_models
        self.timeout = timeout
        self._custom_factory = client_factory
        self._shared_client: httpx.AsyncClient | None = None

    def _get_client(self, timeout: float) -> tuple[httpx.AsyncClient, bool]:
        if self._custom_factory is not None:
            return self._custom_factory(timeout), True
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(timeout=timeout)
        return self._shared_client, False

    async def status(self) -> ProviderStatus:
        """Report API key configuration state without leaking credentials."""
        configured = bool(self.api_key)
        return ProviderStatus(
            name=self.name,
            kind=self.kind,
            available=configured,
            configured=configured,
            default_model=self.default_model,
            models=self.suggested_models,
            detail=(
                f"Chave {self.name.upper()} configurada via ambiente."
                if configured
                else f"Define {self.name.upper()}_API_KEY no ficheiro .env."
            ),
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AIProviderError(
                self.name,
                f"Chave API para {self.name} não configurada nas variáveis de ambiente.",
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
        """Generate a complete response via `/chat/completions`."""
        headers = self._headers()
        payload = self._build_payload(messages, model, stream=False)
        client, should_close = self._get_client(float(self.timeout))
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            if response.status_code >= 400:
                raise AIProviderError(
                    self.name,
                    f"Erro {self.name} ({response.status_code}): {response.text}",
                )
            data = response.json()
            choices = data.get("choices") or []
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            if not content:
                raise AIProviderError(self.name, f"{self.name} devolveu resposta vazia.")
            return str(content)
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(self.name, f"Timeout ao contactar {self.name}.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(self.name, f"Falha de rede ao contactar {self.name}: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def stream(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream SSE deltas from `/chat/completions`."""
        headers = self._headers()
        payload = self._build_payload(messages, model, stream=True)
        client, should_close = self._get_client(float(self.timeout))
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise AIProviderError(
                        self.name,
                        f"Erro {self.name} ({response.status_code}): {body}",
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    chunk = json.loads(raw)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content", "")
                    if delta:
                        yield str(delta)
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(self.name, f"Timeout no streaming {self.name}.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(self.name, f"Falha de rede no streaming {self.name}: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()
