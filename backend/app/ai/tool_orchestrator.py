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
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload.get("tool"):
        return None
    raw_args = payload.get("args") or {}
    if not isinstance(raw_args, dict):
        raw_args = {}
    return ParsedToolCall(tool=str(payload["tool"]).strip(), args=raw_args)
