"""System prompt builder grounding J.A.R.V.I.S. with personality and real telemetry."""

from __future__ import annotations

import random
from collections import deque
from datetime import datetime
from typing import Any, Deque, Mapping, Sequence

_RECENT_GREETINGS: Deque[str] = deque(maxlen=6)


def remember_greeting(text: str) -> None:
    """Track recent greetings so the AI avoids repeating itself."""
    clean = text.strip()
    if clean:
        _RECENT_GREETINGS.append(clean)


def _time_period_pt(hour: int) -> str:
    if 5 <= hour < 12:
        return "manhã"
    if 12 <= hour < 19:
        return "tarde"
    if 19 <= hour < 24:
        return "noite"
    return "madrugada"


def build_jarvis_system_prompt(
    system_snapshot: Mapping[str, Any] | None = None,
    tools_catalog: str = "",
    memories_block: str = "",
) -> str:
    """Build the Muquissi system prompt with live context, memories, and optional tools."""
    now = datetime.now()
    telemetry_line = ""
    if system_snapshot:
        temp = (
            f", temperatura {system_snapshot['temperature_celsius']} °C"
            if system_snapshot.get("temperature_celsius") is not None
            else ""
        )
        telemetry_line = (
            f"\nContexto atual do computador ({system_snapshot.get('hostname', 'Ubuntu')}): "
            f"CPU {system_snapshot.get('cpu_percent')}%, "
            f"RAM {system_snapshot.get('ram_percent')}% "
            f"({system_snapshot.get('ram_used_gb')}/{system_snapshot.get('ram_total_gb')} GB), "
            f"Disco livre {system_snapshot.get('disk_free_gb')} GB, "
            f"Rede {'ligada' if system_snapshot.get('network_connected') else 'desligada'}"
            f"{temp}."
        )

    tools_block = ""
    if tools_catalog:
        tools_block = (
            "\n\nFerramentas disponíveis (usa APENAS quando o pedido exigir ação real, "
            "leitura de ficheiros, Git, serviços ou abrir aplicações):\n"
            f"{tools_catalog}\n"
            "Quando precisares executar uma ferramenta, responde EXCLUSIVAMENTE com:\n"
            '<tool_call>{"tool": "nome_da_ferramenta", "args": {...}}</tool_call>\n'
            "Não escrevas texto fora das tags <tool_call>...</tool_call> quando chamares uma ferramenta. "
            "Para conversas normais ou perguntas já respondidas pelo contexto acima, responde diretamente em texto."
        )

    memory_section = ""
    if memories_block:
        memory_section = (
            "\n\nMemórias aprovadas pelo Carlos (usa como contexto natural):\n"
            f"{memories_block}"
        )

    return (
        "És o Muquissi, o parceiro de IA pessoal "
        "do Carlos no seu computador Ubuntu Linux (ele é programador Python/Django, web, APIs e automação).\n"
        "Personalidade: inteligente, amigável, natural, espirituoso na medida certa, próximo e "
        "objetivo — falas como um verdadeiro cérebro assistente com iniciativa, nunca como um "
        "robô rígido ou formulário burocrático.\n"
        "Variante linguística: Português natural (pt-PT / pt-AO), tratando o Carlos por 'tu' "
        "(ex.: 'ficheiro', 'telemóvel', 'ecrã', 'frigorífico'; evita expressões brasileiras como 'você' ou 'geladeira').\n"
        "Regras operacionais:\n"
        "- Vai direto ao ponto com clareza e naturalidade; respostas faladas devem ser fluidas e sem listas longas.\n"
        "- Nunca inventes resultados de comandos, ficheiros ou ferramentas que não foram executadas.\n"
        "- Nunca tentes contornar permissões de segurança (Nível 2 pede confirmação do Carlos; Nível 3 é proibido).\n"
        f"Momento atual: {_time_period_pt(now.hour)}, {now.strftime('%d/%m/%Y %H:%M')}."
        f"{telemetry_line}"
        f"{memory_section}"
        f"{tools_block}"
    )


def build_dynamic_greeting_prompt(
    system_snapshot: Mapping[str, Any] | None = None,
    recent_titles: Sequence[str] | None = None,
) -> str:
    """Prompt instructing the AI brain to speak freely and creatively without canned templates."""
    now = datetime.now()
    period = _time_period_pt(now.hour)
    hints = f" Últimos tópicos de conversa: {', '.join(recent_titles[:3])}." if recent_titles else ""
    cpu = system_snapshot.get("cpu_percent") if system_snapshot else None
    ram = system_snapshot.get("ram_percent") if system_snapshot else None
    sys_note = f" (PC agora: CPU {cpu}%, RAM {ram}%)" if cpu is not None else ""

    angles = [
        "faz um comentário espontâneo e bem-humorado sobre o momento do dia",
        "lança uma provocação criativa sobre o que construir ou automatizar hoje",
        "comenta de forma leve como a máquina está a responder agora",
        "puxa conversa como um parceiro de engenharia curioso com uma ideia rápida",
        "dá uma saudação descontraída e pergunta qual é o foco da hora",
    ]
    chosen_angle = random.choice(angles)

    avoid_block = ""
    if _RECENT_GREETINGS:
        avoid_list = " | ".join(_RECENT_GREETINGS)
        avoid_block = f" NÃO repitas nem imites nenhuma destas frases anteriores: [{avoid_list}]."

    return (
        f"São {now.strftime('%H:%M')} ({period}){sys_note}.{hints} "
        f"Fala diretamente com o Carlos com total liberdade: {chosen_angle}. "
        "Usa 1 ou 2 frases curtas, naturais e com personalidade própria — sem clichés robóticos "
        "e sem copiar fórmulas fixas."
        f"{avoid_block}"
    )


def fallback_dynamic_greeting(system_snapshot: Mapping[str, Any] | None = None) -> str:
    """Varied natural greeting used only if all AI providers are unreachable."""
    hour = datetime.now().hour
    period_greet = (
        "Bom dia"
        if 5 <= hour < 12
        else "Boa tarde"
        if 12 <= hour < 19
        else "Boa noite"
    )
    cpu = system_snapshot.get("cpu_percent") if system_snapshot else None
    options = [
        f"Fala aí, Carlos! Qual é a ideia de hoje?",
        f"{period_greet}, Carlos! Em que código ou plano vamos mexer agora?",
        f"Estou na escuta, Carlos. Que desafio queres atacar neste momento?",
        f"E aí, Carlos! Manda uma boa ideia para testarmos juntos.",
    ]
    if cpu is not None:
        options.append(
            f"{period_greet}, Carlos! A máquina está tranquila com {cpu}% de CPU. O que vamos criar agora?"
        )
    candidates = [opt for opt in options if opt not in _RECENT_GREETINGS] or options
    choice = random.choice(candidates)
    remember_greeting(choice)
    return choice
