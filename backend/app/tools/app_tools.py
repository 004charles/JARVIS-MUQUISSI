"""Allowlisted Ubuntu desktop application launcher tools (Level 1 Safe)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict

from app.security.permissions import (
    ALLOWED_DESKTOP_APPS,
    PermissionLevel,
    SecurityPolicy,
    SecurityViolation,
)
from app.tools.base import JarvisTool, ToolResult


class ListAppsTool(JarvisTool):
    """List pre-authorized desktop applications installed on the computer."""

    name = "list_apps"
    description = "Consultar aplicações autorizadas disponíveis no computador."
    parameters_hint = "{}"
    permission_level = PermissionLevel.SAFE

    async def execute(self, _params: Dict[str, Any]) -> ToolResult:
        available: Dict[str, str] = {}
        for friendly, candidates in ALLOWED_DESKTOP_APPS.items():
            for binary in candidates:
                found = shutil.which(binary)
                if found:
                    available[friendly] = found
                    break
        return ToolResult(success=True, output={"available_apps": available})


class OpenApplicationTool(JarvisTool):
    """Open an allowlisted desktop application safely without a shell."""

    name = "open_application"
    description = "Abrir uma aplicação autorizada (ex: vscode, terminal, files, firefox, chrome, calculator)."
    parameters_hint = '{"app": "nome-da-aplicacao"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_app = str(params.get("app", "")).strip()
        if not raw_app:
            return ToolResult(success=False, error="Parâmetro 'app' é obrigatório.")

        try:
            candidates = self._policy.resolve_allowed_app(raw_app)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        resolved_bin = next((shutil.which(cmd) for cmd in candidates if shutil.which(cmd)), None)
        if not resolved_bin:
            return ToolResult(
                success=False,
                error=f"Aplicação '{raw_app}' autorizada, mas nenhum executável encontrado no sistema.",
            )

        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return ToolResult(
                success=False,
                error="Sessão gráfica (DISPLAY/WAYLAND_DISPLAY) não detetada neste processo.",
            )

        subprocess.Popen(
            [resolved_bin],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return ToolResult(
            success=True,
            output={"app": raw_app, "executable": resolved_bin, "launched": True},
        )
