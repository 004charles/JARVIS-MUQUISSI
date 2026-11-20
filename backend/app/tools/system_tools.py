"""System telemetry and service-inspection tools (Level 1 Safe)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.security.permissions import PermissionLevel, SecurityPolicy, SecurityViolation
from app.system.telemetry import get_system_snapshot
from app.tools.base import JarvisTool, ToolResult


class SystemStatusTool(JarvisTool):
    """Read real-time CPU, RAM, disk, network, temperature, and top processes."""

    name = "system_status"
    description = "Consultar estado atual do computador (CPU, RAM, disco, temperatura, rede e processos)."
    parameters_hint = "{}"
    permission_level = PermissionLevel.SAFE

    async def execute(self, _params: Dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=get_system_snapshot())


class CheckServiceTool(JarvisTool):
    """Check whether a Linux systemd service is active (read-only)."""

    name = "check_service"
    description = "Verificar se um serviço do Ubuntu (ex: postgresql, docker, ollama, nginx) está ativo."
    parameters_hint = '{"service": "nome-do-servico"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_service = str(params.get("service", "")).strip()
        if not raw_service:
            return ToolResult(success=False, error="Parâmetro 'service' é obrigatório.")
        try:
            service = self._policy.validate_service_name(raw_service)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        try:
            proc = await asyncio.create_subprocess_exec(
                "systemctl",
                "is-active",
                service,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            state_text = stdout.decode("utf-8", errors="replace").strip()
            err_text = stderr.decode("utf-8", errors="replace").strip()
            return ToolResult(
                success=True,
                output={
                    "service": service,
                    "active": proc.returncode == 0 and state_text == "active",
                    "status": state_text or err_text or "unknown",
                },
            )
        except FileNotFoundError:
            return ToolResult(success=False, error="Comando 'systemctl' não encontrado.")
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Timeout ao verificar serviço.")
