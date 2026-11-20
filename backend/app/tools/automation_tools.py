"""Phase 8 controlled tools for projects, tests, web research, tasks, and agenda."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation.project_analyzer import analyze_project_directory
from app.automation.web_research import search_web
from app.database.models import AgendaEvent, TaskItem
from app.database.session import SessionLocal
from app.security.permissions import PermissionLevel, SecurityPolicy, SecurityViolation
from app.tools.base import JarvisTool, ToolResult


class AnalyzeProjectTool(JarvisTool):
    """Non-destructive project structure, stack, and Git analysis (Level 1 Safe)."""

    name = "analyze_project"
    description = "Analisar estrutura, tecnologias, dependências e Git de um projeto autorizado."
    parameters_hint = '{"directory": "caminho-do-projeto"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_dir = str(
            params.get("directory")
            or (self._policy.allowed_directories[0] if self._policy.allowed_directories else ".")
        )
        try:
            report = await analyze_project_directory(raw_dir, self._policy)
            return ToolResult(success=True, output=report)
        except (SecurityViolation, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))


class RunProjectTestsTool(JarvisTool):
    """Execute automated project test suite (`pytest` or `npm test`) (Level 2 Confirmation)."""

    name = "run_project_tests"
    description = "Executar testes automatizados (pytest ou npm test) num projeto autorizado (requer confirmação)."
    parameters_hint = '{"directory": "caminho-do-projeto", "runner": "pytest|npm"}'
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_dir = str(
            params.get("directory")
            or (self._policy.allowed_directories[0] if self._policy.allowed_directories else ".")
        )
        runner = str(params.get("runner", "pytest")).strip().lower()
        try:
            project_dir: Path = self._policy.validate_authorized_path(raw_dir)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        if runner == "npm":
            cmd = ["npm", "test"]
        elif runner == "pytest":
            venv_pytest = project_dir / ".venv" / "bin" / "pytest"
            cmd = [str(venv_pytest) if venv_pytest.exists() else "pytest", "-q"]
        else:
            return ToolResult(success=False, error="Runner suportado: 'pytest' ou 'npm'.")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            return ToolResult(
                success=proc.returncode == 0,
                output={
                    "directory": str(project_dir),
                    "runner": runner,
                    "exit_code": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace")[-2500:],
                    "stderr": stderr.decode("utf-8", errors="replace")[-1000:],
                },
                error=None if proc.returncode == 0 else f"Testes falharam (código {proc.returncode}).",
            )
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Executável '{cmd[0]}' não encontrado.")
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Timeout de 60s ao executar testes.")


class WebSearchTool(JarvisTool):
    """Search public web documentation and results safely (Level 1 Safe)."""

    name = "web_search"
    description = "Pesquisar informações e documentação técnica na Web."
    parameters_hint = '{"query": "termos-de-pesquisa"}'
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        query = str(params.get("query", "")).strip()
        if not query:
            return ToolResult(success=False, error="Parâmetro 'query' é obrigatório.")
        try:
            results = await search_web(query, limit=5)
            return ToolResult(success=True, output={"query": query, "results": results})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Falha na pesquisa Web: {exc}")


class CreateTaskTool(JarvisTool):
    """Create a task or reminder in local productivity DB (Level 1 Safe)."""

    name = "create_task"
    description = "Criar uma nova tarefa ou lembrete na lista de tarefas."
    parameters_hint = '{"title": "titulo-da-tarefa", "priority": "low|medium|high"}'
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        title = str(params.get("title", "")).strip()
        if not title:
            return ToolResult(success=False, error="Parâmetro 'title' é obrigatório.")
        priority = str(params.get("priority", "medium")).strip().lower()
        if priority not in ("low", "medium", "high"):
            priority = "medium"
        task = TaskItem(
            title=title[:200],
            description=str(params.get("description", "")).strip(),
            priority=priority,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return ToolResult(
            success=True,
            output={"id": task.id, "title": task.title, "priority": task.priority, "status": task.status},
        )


class ListTasksTool(JarvisTool):
    """List pending and active tasks (Level 1 Safe)."""

    name = "list_tasks"
    description = "Consultar tarefas pendentes e em progresso."
    parameters_hint = "{}"
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()

    async def execute_with_db(self, db: Session, _params: Dict[str, Any]) -> ToolResult:
        rows = list(
            db.scalars(select(TaskItem).order_by(TaskItem.id.desc()).limit(25)).all()
        )
        return ToolResult(
            success=True,
            output={
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "priority": t.priority,
                    }
                    for t in rows
                ]
            },
        )


class CreateAgendaEventTool(JarvisTool):
    """Schedule an event or reminder on the agenda (Level 1 Safe)."""

    name = "create_agenda_event"
    description = "Agendar um compromisso ou lembrete na agenda."
    parameters_hint = '{"title": "evento", "start_at": "YYYY-MM-DDTHH:MM"}'
    permission_level = PermissionLevel.SAFE

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return await self.execute_with_db(db, params)
        finally:
            db.close()

    async def execute_with_db(self, db: Session, params: Dict[str, Any]) -> ToolResult:
        title = str(params.get("title", "")).strip()
        raw_start = str(params.get("start_at", "")).strip()
        if not title:
            return ToolResult(success=False, error="Parâmetro 'title' é obrigatório.")
        try:
            start_dt = (
                datetime.fromisoformat(raw_start)
                if raw_start
                else datetime.now(timezone.utc)
            )
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return ToolResult(success=False, error="Formato de data inválido (usa ISO YYYY-MM-DDTHH:MM).")

        event = AgendaEvent(
            title=title[:200],
            description=str(params.get("description", "")).strip(),
            start_at=start_dt,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return ToolResult(
            success=True,
            output={"id": event.id, "title": event.title, "start_at": event.start_at.isoformat()},
        )
