"""Shared OpenAI-compatible provider supporting OpenAI and Groq endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, List, Sequence

import httpx

from app.ai.base import AIProvider, AIProviderError, ChatMessage, ProviderStatus

# quota (413/429) or overloaded/unavailable (5xx): try the next model in the chain
_RETRY_STATUSES = (413, 429, 500, 502, 503, 504)
_OVERLOAD_PAUSE_SECONDS = 3.0


def _as_tool_call_text(name: str, arguments: str) -> str:
    """Bridge a native function call into the internal <tool_call> text protocol."""
    try:
        args = json.loads(arguments) if arguments.strip() else {}
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    return "<tool_call>" + json.dumps({"tool": name, "args": args}, ensure_ascii=False) + "</tool_call>"


class OpenAICompatProvider(AIProvider):
    """Unified provider for OpenAI and Groq chat completions APIs."""

    kind = "external"
    supports_native_tools = True

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        suggested_models: List[str],
        timeout: int = 60,
        client_factory: Callable[[float], httpx.AsyncClient] | None = None,
        fallback_models: List[str] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.default_model = default_model
        self.suggested_models = suggested_models
        self.timeout = timeout
        self._custom_factory = client_factory
        self._shared_client: httpx.AsyncClient | None = None
        self.fallback_models = list(fallback_models or [])
        self._rate_limited_until: dict[str, float] = {}

    def _model_chain(self, model: str | None) -> List[str]:
        """Requested model first, then fallbacks; models still rate-limited go last."""
        chain: List[str] = []
        for candidate in [model or self.default_model, *self.fallback_models]:
            if candidate and candidate not in chain:
                chain.append(candidate)
        now = time.monotonic()
        ready = [m for m in chain if self._rate_limited_until.get(m, 0.0) <= now]
        return ready + [m for m in chain if m not in ready]

    def _retry_chain(self, model: str) -> list[str]:
        """Model chain plus one final retry of the first model (overloads are usually momentary)."""
        chain = self._model_chain(model)
        return chain + chain[:1]

    def _mark_rate_limited(self, model: str, response: httpx.Response) -> None:
        retry = response.headers.get("retry-after", "")
        try:
            seconds = float(retry)
        except ValueError:
            seconds = 30.0
        self._rate_limited_until[model] = time.monotonic() + max(1.0, min(seconds, 120.0))

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
        self,
        messages: Sequence[ChatMessage],
        model: str | None,
        stream: bool,
        tools: List[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        chosen = model or self.default_model
        payload: dict[str, object] = {
            "model": chosen,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
        }
        if self.name == "groq" and "gpt-oss" in chosen:
            # Raciocínio curto: respostas em ~0,5 s, essencial para conversa falada.
            payload["reasoning_effort"] = "low"
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        model: str | None = None,
        tools: List[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a complete response via `/chat/completions`."""
        headers = self._headers()
        client, should_close = self._get_client(float(self.timeout))
        try:
            chain = self._retry_chain(model)
            for index, candidate in enumerate(chain):
                if index and index == len(chain) - 1:
                    await asyncio.sleep(_OVERLOAD_PAUSE_SECONDS)  # every model busy: breathe, then once more
                payload = self._build_payload(messages, candidate, stream=False, tools=tools)
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                if response.status_code in _RETRY_STATUSES and index + 1 < len(chain):
                    self._mark_rate_limited(candidate, response)
                    continue
                break
            if response.status_code >= 400:
                raise AIProviderError(
                    self.name,
                    f"Erro {self.name} ({response.status_code}): {response.text}",
                )
            data = response.json()
            choices = data.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content") or ""
            for call in message.get("tool_calls") or []:
                fn = call.get("function") or {}
                if fn.get("name"):
                    return _as_tool_call_text(str(fn["name"]), str(fn.get("arguments") or ""))
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
        self,
        messages: Sequence[ChatMessage],
        model: str | None = None,
        tools: List[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream SSE deltas from `/chat/completions`."""
        headers = self._headers()
        client, should_close = self._get_client(float(self.timeout))
        try:
            chain = self._retry_chain(model)
            for index, candidate in enumerate(chain):
                if index and index == len(chain) - 1:
                    await asyncio.sleep(_OVERLOAD_PAUSE_SECONDS)  # every model busy: breathe, then once more
                payload = self._build_payload(messages, candidate, stream=True, tools=tools)
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code in _RETRY_STATUSES and index + 1 < len(chain):
                        self._mark_rate_limited(candidate, response)
                        await response.aread()
                        continue
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise AIProviderError(
                            self.name,
                            f"Erro {self.name} ({response.status_code}): {body}",
                        )
                    calls: dict[int, dict[str, str]] = {}
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
                        delta_obj = choices[0].get("delta", {})
                        for call in delta_obj.get("tool_calls") or []:
                            slot = calls.setdefault(int(call.get("index", 0)), {"name": "", "args": ""})
                            fn = call.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
                        delta = delta_obj.get("content") or ""
                        if delta and not calls:
                            yield str(delta)
                    if calls:
                        first = calls[min(calls)]
                        if first["name"]:
                            yield _as_tool_call_text(first["name"], first["args"])
                return
        except AIProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise AIProviderError(self.name, f"Timeout no streaming {self.name}.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(self.name, f"Falha de rede no streaming {self.name}: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()
