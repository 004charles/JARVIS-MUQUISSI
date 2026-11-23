"""Model-agnostic tool call parser for AI responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


@dataclass(frozen=True)
class ParsedToolCall:
    """Validated tool name and JSON arguments parsed from an AI output."""

    tool: str
    args: Dict[str, Any]


def extract_tool_call(text: str) -> ParsedToolCall | None:
    """Extract a `<tool_call>{...}</tool_call>` instruction if present."""
    match = _TOOL_CALL_RE.search(text)
    if match:
        raw_json = match.group(1)
    else:
        # Some models (gpt-oss) answer with the bare JSON, sometimes inside ```json fences.
        bare = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        if not (bare.startswith("{") and bare.endswith("}") and '"tool"' in bare):
            return None
        raw_json = bare
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("tool"):
        return None
    raw_args = payload.get("args") or {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    return ParsedToolCall(tool=str(payload["tool"]).strip(), args=raw_args)
