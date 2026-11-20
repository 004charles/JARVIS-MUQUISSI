"""Anthropic Messages API provider with SSE streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Sequence

import httpx

from app.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderStatus


class AnthropicProvider(AIProvider):
    """Connects to Anthropic `/v1/messages` using environment API key."""

    name = "anthropic"
    kind = "external"

    def __init__(
        self,
        api_key: str,
        default_model: str,
        timeout: int = 60,
        base_url: str = "https://api.anthropic.com/v1",
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.default_model = default_model
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (
            lambda t: httpx.AsyncClient(timeout=t)
        )

    async def status(self) -> ProviderStatus:
        """Report Anthropic configuration state."""
        configured = bool(self.api_key)
        return ProviderStatus(
            name=self.name,
            kind=self.kind,
            available=configured,
            configured=configured,
            default_model=self.default_model,
            models=[
                "claude-3-5-sonnet-latest",
                "claude-3-5-haiku-latest",
            ],
            detail=(
                "Chave ANTHROPIC configurada via ambiente."
                if configured
                else "Define ANTHROPIC_API_KEY no ficheiro .env."
            ),
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AIProviderError(
                self.name,
                "Chave API para Anthropic não configurada nas variáveis de ambiente.",
            )
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_payload(
        self, messages: Sequence[ChatMessage], model: str | None, stream: bool
    ) -> dict[str, object]:
        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload: dict[str, object] = {
            "model": model or self.default_model,
            "max_tokens": 1024,
            "messages": chat_messages,
            "stream": stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    async def generate(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> str:
        """Generate a complete response from Anthropic `/messages`."""
        headers = self._headers()
        payload = self._build_payload(messages, model, stream=False)
        try:
            async with self._client_factory(float(self.timeout)) as client:
                response = await client.post(
                    f"{self.base_url}/messages", headers=headers, json=payload
                )
                if response.status_code >= 400:
                    raise AIProviderError(
                        self.name,
                        f"Erro Anthropic ({response.status_code}): {response.text}",
                    )
                data = response.json()
                blocks = data.get("content") or []
                text = "".join(
                    b.get("text", "") for b in blocks if b.get("type") == "text"
                )
                if not text:
                    raise AIProviderError(self.name, "Anthropic devolveu resposta vazia.")
                return text
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(self.name, "Timeout ao contactar Anthropic.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(self.name, f"Falha de rede Anthropic: {exc}") from exc

    async def stream(
        self, messages: Sequence[ChatMessage], model: str | None = None
    ) -> AsyncIterator[str]:
        """Stream SSE deltas from Anthropic `/messages`."""
        headers = self._headers()
        payload = self._build_payload(messages, model, stream=True)
        try:
            async with self._client_factory(float(self.timeout)) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise AIProviderError(
                            self.name,
                            f"Erro Anthropic ({response.status_code}): {body}",
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        event = json.loads(raw)
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {}).get("text", "")
                            if delta:
                                yield str(delta)
                        elif event.get("type") == "message_stop":
                            break
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(self.name, "Timeout no streaming Anthropic.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(self.name, f"Falha de rede no streaming Anthropic: {exc}") from exc
