"""Multi-step agent loop: think → use a tool → look at the real result → repeat → answer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, List, Sequence

from sqlalchemy.orm import Session

from app.ai.base import ChatMessage
from app.ai.manager import ai_manager
from app.ai.tool_orchestrator import extract_tool_call
from app.core.logging import get_logger
from app.security.permissions import PendingApproval
from app.tools.registry import tool_registry

logger = get_logger("ai.agent_loop")

MAX_AGENT_STEPS = 6
# Anti prompt-injection: any tool output may carry text written by strangers (web pages,
# files, emails). After reading such output, side-effecting tools in the same turn need
# Carlos's spoken "sim". Allowlist of tools whose output is only Arcanjo's own data:
_TRUSTED_OUTPUT_TOOLS = {
    "system_status",
    "list_apps",
    "list_tasks",
    "create_task",
    "create_agenda_event",
    "open",
    "open_application",
    "save_memory",
    "check_service",
    # The Céu's own curated Bible text is trusted data
    "biblia_ler",
    "biblia_procurar",
    "biblia_relacionados",
    "biblia_original",
    "biblia_palavra",
    "mostrar_visao",
}
# Fail closed: shell output is untrusted unless the command is one of a few exact, local,
# read-only/no-content commands (anchored allowlist; pipes, redirects of input, ; && etc. excluded).
_TRUSTED_COMMAND_RE = re.compile(
    r"(?:"
    # Only commands whose output cannot carry file names or other attacker-controlled text
    # (no ls: a directory listing returns file names, which can hold injected instructions)
    r"pwd"
    r"|date"
    r"|uptime(?:[ \t]+-p)?"
    r"|df(?:[ \t]+-h)?"
    r"|free(?:[ \t]+-h)?"
    r"|mkdir(?:[ \t]+-p)?(?:[ \t]+[\w./~-]+)+"
    r"|echo[ \t]+[\w .,:!?-]*(?:[ \t]*>[ \t]*[\w./~-]+)?"
    r"|(?:wpctl|pactl)[ \t]+(?:get|set)-[\w-]+(?:[ \t]+[@\w.%+-]+)*"
    r")"
)
# Anything that can chain, substitute or redirect commands is never "trusted" (except echo > file above)
_SHELL_META = re.compile(r"[\n\r\x00;&|`$<()]")


def _output_is_untrusted(tool: str, args: dict[str, Any]) -> bool:
    if tool == "run_command":
        if set(args) - {"command"}:
            return True  # cwd/env/etc. change what the command sees: never trusted
        cmd = str(args.get("command", "")).strip(" \t")
        if _SHELL_META.search(cmd):
            return True
        return not _TRUSTED_COMMAND_RE.fullmatch(cmd)
    return tool not in _TRUSTED_OUTPUT_TOOLS
_RESULT_CHARS = 3500


@dataclass
class AgentTurnResult:
    """Final spoken/written answer plus what happened along the way."""

    reply: str
    provider: str = ""
    model: str = ""
    steps: List[dict[str, Any]] = field(default_factory=list)
    pending_approval: PendingApproval | None = None


def _compact(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text if len(text) <= _RESULT_CHARS else f"{text[:_RESULT_CHARS]}…(truncado)"


_CEU_WORDS = re.compile(
    r"\b(b[ií]blia|b[ií]blic\w*|vers[ií]culo|escritura\w*|deus|jesus|cristo|senhor|esp[ií]rito|anjo\w*|arcanjo|"
    r"c[eé]u|f[eé]|ora[cç][aã]o|rezar|orar|salmo\w*|evangelho\w*|ap[oó]stolo\w*|profe\w*|apocalipse|pecado\w*|"
    r"salva[cç][aã]o|igreja|par[aá]bola\w*|milagre\w*|mois[eé]s|abra[aã]o|davi|paulo|pedro|maria|"
    r"hebraico|grego|strong|teolog\w*|alma|morte|ressurrei\w*|perd[aã]o|gra[cç]a|santo\w*|tr[ií]ndade|"
    r"miguel|gabriel|serafi\w*|querubi\w*|diabo|satan[aá]s|dem[oó]ni\w*)\b",
    re.IGNORECASE,
)


def choose_toolset(messages: Sequence[ChatMessage]) -> set[str] | None:
    """Scripture/spiritual conversations only get the Céu tools (smaller, cheaper, more focused
    requests); everything else gets the full toolset."""
    from app.ceu.reference import find_references
    from app.tools.registry import CEU_TOOLSET

    last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    if _CEU_WORDS.search(last_user) or find_references(last_user):
        return set(CEU_TOOLSET)
    return None


_READ_TOOLS = {"biblia_ler", "biblia_original", "biblia_relacionados", "biblia_procurar", "mostrar_visao"}


def _unread_references(reply: str, steps: list[dict[str, Any]]) -> list[str]:
    """References quoted in the answer that were not looked up in the Céu during this turn."""
    from app.ceu.reference import find_references, parse_reference

    if not any(q in reply for q in ("«", "“", '"')):
        return []  # no quotation: mentioning a reference is fine
    read_keys: set[tuple[int, int]] = set()
    for st in steps:
        if st.get("tool") in _READ_TOOLS and st.get("status") == "executed":
            args = st.get("args") or {}
            refs = args.get("referencias") or [args.get("ref", "")]
            if isinstance(refs, str):
                refs = refs.replace(";", ",").split(",")
            try:
                for r in (rng for one in refs if str(one).strip() for rng in parse_reference(str(one))):
                    for ch in range(r.start_chapter, r.end_chapter + 1):
                        read_keys.add((r.book.ordinal, ch))
            except Exception:  # noqa: BLE001
                continue
            if st.get("tool") == "biblia_procurar":
                return []  # a search was made; the quotes likely come from its results
    unread = []
    for r in find_references(reply):
        if (r.book.ordinal, r.start_chapter) not in read_keys:
            unread.append(r.label())
    return list(dict.fromkeys(unread))


def describe_pending_action(approval: PendingApproval) -> str:
    """Natural spoken confirmation question for a destructive action."""
    # Long absolute paths are unbearable to hear: say just the last folder/file name.
    target = re.sub(r"(?:/[^\s/'\"]+){2,}/([^\s/'\"]+)", r"\1", approval.target.strip())
    if approval.tool_name == "run_command":
        return f"Antes de avançar: isto é sensível, vou executar «{target}». Confirmas?"
    return f"Isto mexe em «{target}». Queres mesmo que avance?"


async def run_agent_turn(
    db: Session,
    messages: Sequence[ChatMessage],
    provider_override: str | None = None,
    model_override: str | None = None,
    max_steps: int = MAX_AGENT_STEPS,
    manager: Any = None,
    registry: Any = None,
) -> AgentTurnResult:
    """Let the model chain tool calls until it produces a final natural-language answer."""
    manager = manager or ai_manager
    registry = registry or tool_registry
    if model_override is None:
        from app.ai.routing import route_model

        provider_name = provider_override
        if provider_name is None and hasattr(manager, "get_active_config"):
            try:
                provider_name = str(manager.get_active_config(db)["default_provider"])
            except Exception:  # noqa: BLE001
                provider_name = None
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        model_override = route_model(last_user, provider_name)
    context: list[ChatMessage] = list(messages)
    fidelity_checked = False
    from app.brain.state import mind_state

    # Text held up to the camera could be an injected instruction: gate side effects this turn.
    tainted = mind_state.vision_tainted()
    names = choose_toolset(context)
    native_tools = registry.native_tool_specs(names) if hasattr(registry, "native_tool_specs") else None
    result = AgentTurnResult(reply="")

    for step in range(max_steps + 1):
        reply, provider, model, _ = await manager.generate_chat(
            db=db,
            messages=context,
            provider_override=provider_override,
            model_override=model_override,
            tools=native_tools,
        )
        result.provider, result.model = provider, model
        if not reply.strip():
            # Reasoning models sometimes "think" the tool call but emit no content: nudge once.
            reply, provider, model, _ = await manager.generate_chat(
                db=db,
                messages=[
                    *context,
                    ChatMessage(
                        role="user",
                        content=(
                            "(Não recebi resposta. Responde agora: ou o texto para o Carlos, ou "
                            "a chamada <tool_call>{...}</tool_call> se precisares de agir.)"
                        ),
                    ),
                ],
                provider_override=provider_override,
                model_override=model_override,
                tools=native_tools,
            )
        parsed = extract_tool_call(reply)
        if parsed is None:
            unread = _unread_references(reply, result.steps) if not fidelity_checked else []
            if unread and step < max_steps:
                # Fidelity guard: Scripture is never quoted from memory — read it, then answer again.
                fidelity_checked = True
                context.append(ChatMessage(role="assistant", content=reply))
                context.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "(Antes de responderes, LÊ no Céu com biblia_ler as passagens que citaste e que ainda "
                            f"não leste: {', '.join(unread[:4])}. Depois refaz a resposta citando o texto exato da "
                            "Bíblia Livre entre «» e as referências corretas.)"
                        ),
                    )
                )
                continue
            result.reply = reply.strip()
            return result

        if step == max_steps:
            # Out of budget: force a plain answer about what was achieved.
            context.append(ChatMessage(role="assistant", content=reply))
            context.append(
                ChatMessage(
                    role="user",
                    content="Chega de ferramentas. Diz ao Carlos, em poucas frases, o que conseguiste e o que falta.",
                )
            )
            final, provider, model, _ = await manager.generate_chat(
                db=db,
                messages=context,
                provider_override=provider_override,
                model_override=model_override,
            )
            result.provider, result.model = provider, model
            result.reply = re.sub(r"<tool_call>.*?</tool_call>", "", final, flags=re.DOTALL).strip()
            break

        outcome = await registry.invoke(
            db=db, tool_name=parsed.tool, params=parsed.args, force_confirmation=tainted
        )
        tainted = tainted or _output_is_untrusted(parsed.tool, parsed.args)
        logger.info("Agente passo %d: %s → %s", step + 1, parsed.tool, outcome.status)
        result.steps.append({"tool": parsed.tool, "args": parsed.args, "status": outcome.status})

        if outcome.status == "awaiting_confirmation" and outcome.approval is not None:
            result.pending_approval = outcome.approval
            result.reply = describe_pending_action(outcome.approval)
            return result

        if outcome.status == "blocked":
            observation: Any = {"bloqueado": True, "motivo": outcome.message}
        elif outcome.result is not None:
            observation = outcome.result.model_dump()
        else:
            observation = {"success": False, "error": outcome.message}

        context.append(ChatMessage(role="assistant", content=reply))
        context.append(
            ChatMessage(
                role="user",
                content=(
                    f"[Resultado real de '{parsed.tool}']: {_compact(observation)}\n"
                    "Se ainda faltar algo para cumprir o pedido do Carlos, chama a próxima ferramenta. "
                    "Se falhou, tenta outra abordagem. Quando estiver feito, responde-lhe em "
                    "linguagem natural, curto, sem inventar nada que não esteja nos resultados."
                ),
            )
        )

    result.reply = result.reply or "Fiz o que consegui, mas não cheguei a uma resposta final."
    return result
