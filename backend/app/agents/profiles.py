"""Specialized Phase 9 agent profiles and automatic goal routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Literal

AgentType = Literal["coding", "system", "research", "automation", "project"]


@dataclass(frozen=True)
class AgentProfile:
    """Configuration for a specialized autonomous Muquissi sub-agent."""

    id: AgentType
    name: str
    role: str
    description: str
    instructions: str
    allowed_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
        }


AGENT_PROFILES: Dict[AgentType, AgentProfile] = {
    "coding": AgentProfile(
        id="coding",
        name="Agente de Código",
        role="Engenharia & Depuração",
        description="Lê código-fonte, verifica Git, executa testes e diagnostica bugs nos projetos.",
        instructions=(
            "És o Agente Especializado em Código do Muquissi. Investiga os ficheiros reais antes de "
            "diagnosticar, usa git_status, search_files, read_file e run_project_tests sempre que útil, "
            "e só usa create_file (Nível 2) se for explicitamente necessário criar ou propor código novo."
        ),
        allowed_tools=(
            "list_files",
            "search_files",
            "read_file",
            "git_status",
            "analyze_project",
            "run_project_tests",
            "create_file",
        ),
    ),
    "system": AgentProfile(
        id="system",
        name="Agente de Sistema",
        role="Telemetria & Saúde Ubuntu",
        description="Diagnostica CPU, RAM, disco, temperatura, processos e estado de serviços Linux.",
        instructions=(
            "És o Agente Especializado em Sistema Linux Ubuntu. Usa system_status, check_service e "
            "list_apps para recolher métricas reais antes de diagnosticar gargalos ou recomendar ações."
        ),
        allowed_tools=("system_status", "check_service", "list_apps"),
    ),
    "research": AgentProfile(
        id="research",
        name="Agente de Pesquisa",
        role="Investigação Web & Memória",
        description="Pesquisa na internet, cruza fontes e consulta memórias aprovadas do Carlos.",
        instructions=(
            "És o Agente Especializado em Pesquisa do Muquissi. Usa web_search para procurar factos "
            "atuais e search_memory para cruzar com o contexto do Carlos, resumindo tudo com clareza."
        ),
        allowed_tools=("web_search", "search_memory", "look_camera"),
    ),
    "automation": AgentProfile(
        id="automation",
        name="Agente de Automação",
        role="Fluxos, Tarefas & Agenda",
        description="Organiza tarefas, eventos de agenda, ficheiros de trabalho e abertura de apps.",
        instructions=(
            "És o Agente Especializado em Automação do Muquissi. Usa list_tasks, create_task e "
            "create_agenda_event para estruturar ações; cria ficheiros ou abre apps apenas quando pedido."
        ),
        allowed_tools=(
            "list_tasks",
            "create_task",
            "create_agenda_event",
            "list_apps",
            "open_app",
            "create_file",
        ),
    ),
    "project": AgentProfile(
        id="project",
        name="Agente de Projetos",
        role="Arquitetura & Planeamento",
        description="Mapeia repositórios, identifica tecnologias, planeia entregas e cria tarefas.",
        instructions=(
            "És o Agente Especializado em Gestão e Arquitetura de Projetos do Muquissi. Analisa o "
            "repositório com analyze_project, list_files e git_status, e regista próximos passos com create_task."
        ),
        allowed_tools=(
            "analyze_project",
            "list_files",
            "search_files",
            "git_status",
            "list_tasks",
            "create_task",
        ),
    ),
}


def get_agent_profile(agent_type: str) -> AgentProfile:
    """Resolve an AgentProfile or raise ValueError for unknown agent types."""
    key = agent_type.strip().lower()
    if key not in AGENT_PROFILES:
        valid = ", ".join(AGENT_PROFILES.keys())
        raise ValueError(f"Agente desconhecido '{agent_type}'. Opções: {valid}")
    return AGENT_PROFILES[key]  # type: ignore[index]


def infer_agent_type(goal: str) -> AgentType:
    """Infer the best specialized agent when caller doesn't specify one."""
    text = goal.lower()
    if re.search(r"\b(cpu|ram|disco|processo|servico|serviço|ubuntu|memoria|temperatura|sistema)\b", text):
        return "system"
    if re.search(r"\b(pesquisa|internet|web|artigo|noticia|notícia|busca|procura|comparar|preço)\b", text):
        return "research"
    if re.search(r"\b(codigo|código|bug|erro|test|teste|git|python|typescript|refactor|api)\b", text):
        return "coding"
    if re.search(r"\b(tarefa|agenda|lembrete|automat|rotina|abrir app|calendario|calendário)\b", text):
        return "automation"
    return "project"
