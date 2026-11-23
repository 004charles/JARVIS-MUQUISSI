"""Choose the brain for each question: quick/cheap model for simple turns, the deepest for hard ones.

Inspired by the query-complexity router of OpenJarvis (Stanford, Apache-2.0), rewritten for
Portuguese and for the Céu (Scripture, theology, mysteries).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings

_REASONING = re.compile(
    r"\b(porqu[eê]|por que|explica\w*|analis\w*|compar\w*|diferen[cç]a|significa\w*|sentido|contexto|"
    r"interpreta\w*|relaciona\w*|como (?:é|e) que|o que (?:quer|queria) dizer|aprofunda\w*|"
    r"hist[oó]ric\w*|teolog\w*|doutrina\w*|argument\w*|evid[eê]ncia\w*)\b",
    re.IGNORECASE,
)
_DEEP_TOPICS = re.compile(
    r"\b(apocalipse|profeci\w*|144 ?mil|arrebatamento|fim dos tempos|trindade|predestina\w*|livre[- ]arb[ií]trio|"
    r"sofrimento|mal no mundo|j[oó]b?\b|ressurrei\w*|salva[cç][aã]o|gra[cç]a|lei e gra[cç]a|aliança|"
    r"mist[eé]rio\w*|consci[eê]ncia|morte|inferno|para[ií]so|anticristo|n[uú]mero da besta|666|"
    r"hebraico|grego|original|strong)\b",
    re.IGNORECASE,
)
_MULTI_PART = re.compile(r"\b(e tamb[eé]m|al[eé]m disso|primeiro|depois|por fim|e ainda)\b|^\s*\d+[.)]", re.IGNORECASE | re.MULTILINE)
_SMALL_TALK = re.compile(
    r"^\s*(ol[aá]|oi|bom dia|boa tarde|boa noite|obrigad[oa]|am[eé]m|paz|tchau|adeus|sim|n[aã]o|ok)\b[\s!.,?]*$",
    re.IGNORECASE,
)
_REF = re.compile(r"\b\d?\s?[A-ZÁÉÍÓÚÂÊÔ][a-záéíóúâêôãõç]+\.?\s\d{1,3}(?::\d{1,3})?")


@dataclass(frozen=True)
class Complexity:
    score: float  # 0..1
    tier: str  # trivial | simple | moderate | complex
    signals: dict


def score_complexity(text: str) -> Complexity:
    t = text.strip()
    signals: dict = {}
    if not t or _SMALL_TALK.match(t):
        return Complexity(0.0, "trivial", {"small_talk": True})
    score = 0.0
    n = len(t)
    signals["length"] = n
    score += 0.0 if n < 40 else 0.1 if n < 120 else 0.2 if n < 300 else 0.3
    reasoning = len(_REASONING.findall(t))
    signals["reasoning"] = reasoning
    score += min(0.35, 0.18 * reasoning)
    deep = len(_DEEP_TOPICS.findall(t))
    signals["deep_topics"] = deep
    score += min(0.35, 0.2 * deep)
    multi = len(_MULTI_PART.findall(t)) + max(0, t.count("?") - 1)
    signals["multi_part"] = multi
    score += min(0.2, 0.1 * multi)
    refs = len(_REF.findall(t))
    signals["references"] = refs
    if refs > 1:
        score += 0.1
    score = min(1.0, score)
    tier = "trivial" if score < 0.1 else "simple" if score < 0.3 else "moderate" if score < 0.55 else "complex"
    return Complexity(round(score, 2), tier, signals)


# Default fast/deep models per provider (overridable in .env: AI_FAST_MODEL / AI_DEEP_MODEL)
_DEFAULTS = {
    "groq": ("openai/gpt-oss-20b", "openai/gpt-oss-120b"),
    "anthropic": ("claude-haiku-5-5", "claude-sonnet-5-5"),
    "openai": ("gpt-4o-mini", "gpt-4o"),
}


def route_model(text: str, provider: str | None) -> str | None:
    """Model to use for this question (None = provider's configured default)."""
    settings = get_settings()
    if not settings.ai_routing or not provider:
        return None
    fast_default, deep_default = _DEFAULTS.get(provider, (None, None))
    fast = settings.ai_fast_model.strip() or fast_default
    deep = settings.ai_deep_model.strip() or deep_default
    tier = score_complexity(text).tier
    return fast if tier in ("trivial", "simple") else deep
