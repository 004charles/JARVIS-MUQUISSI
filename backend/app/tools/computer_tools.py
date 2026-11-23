"""Full computer control tools: shell commands, any desktop app, files and URLs."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

from app.security.permissions import PermissionLevel, SecurityPolicy
from app.tools.base import JarvisTool, ToolResult

_MAX_OUTPUT_CHARS = 4000
_SUDO_RE = re.compile(r"(^|[;&|(]\s*)sudo(?:\s+-[A-Za-z]+)*\s+")
_DESKTOP_DIRS = (
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    half = _MAX_OUTPUT_CHARS // 2
    return f"{text[:half]}\n…[{len(text) - _MAX_OUTPUT_CHARS} caracteres omitidos]…\n{text[-half:]}"


_SECRET_ENV_RE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)


def _graphical_env() -> dict[str, str]:
    """Desktop session env without Arcanjo's own secrets (API keys never reach commands)."""
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}


def has_graphical_session() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def find_desktop_entry(query: str) -> str | None:
    """Find an installed .desktop app id whose file name or Name= matches the query."""
    needle = query.strip().lower()
    if not needle:
        return None
    best: tuple[int, str] | None = None
    for directory in _DESKTOP_DIRS:
        if not directory.is_dir():
            continue
        for entry in directory.glob("*.desktop"):
            app_id = entry.stem
            try:
                text = entry.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"^NoDisplay=true", text, re.MULTILINE):
                continue
            names = [m.lower() for m in re.findall(r"^Name(?:\[pt[^\]]*\])?=(.+)$", text, re.MULTILINE)]
            score = 0
            if app_id.lower() == needle or needle in names:
                score = 3
            elif any(n.startswith(needle) for n in names) or app_id.lower().endswith(needle):
                score = 2
            elif needle in app_id.lower() or any(needle in n for n in names):
                score = 1
            if score and (best is None or score > best[0]):
                best = (score, app_id)
    return best[1] if best else None


class RunCommandTool(JarvisTool):
    """Run any shell command on the Carlos' computer (full access mode)."""

    name = "run_command"
    description = (
        "Executar QUALQUER comando no terminal bash do computador (instalar, gerir ficheiros, git, "
        "docker, volume com pactl/wpctl, rede, processos, scripts...). 'sudo' abre uma janela a "
        "pedir a password. Usa para tudo o que as outras ferramentas não fazem. Para apagar ou "
        "outras ações destrutivas chama-a DIRETAMENTE: o sistema pede confirmação ao Carlos sozinho."
    )
    parameters_hint = '{"command": "comando bash", "cwd": "pasta opcional", "timeout": 60}'
    permission_level = PermissionLevel.SAFE  # perigos detetados dinamicamente pelo registo

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def describe_target(self, params: Dict[str, Any]) -> str:
        return str(params.get("command", "")).strip() or self.name  # full command: the approval banner must show all of it

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        command = str(params.get("command", "")).strip()
        if not command:
            return ToolResult(success=False, error="Parâmetro 'command' é obrigatório.")
        if not self._policy.full_access:
            return ToolResult(
                success=False,
                error="Acesso total desativado (FULL_ACCESS=false no .env).",
            )
        cwd = Path(str(params.get("cwd") or Path.home())).expanduser()
        if not cwd.is_dir():
            cwd = Path.home()
        try:
            timeout = float(params.get("timeout") or 60)
        except (TypeError, ValueError):
            timeout = 60.0
        timeout = max(1.0, min(timeout, 900.0))

        # Without a TTY, sudo can't ask for the password: use the graphical polkit prompt.
        if shutil.which("pkexec") and has_graphical_session():
            command = _SUDO_RE.sub(r"\1pkexec ", command)

        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_graphical_env(),
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(
                success=False,
                error=f"O comando excedeu {int(timeout)} s e foi terminado.",
            )
        out = _truncate(stdout.decode("utf-8", errors="replace").strip())
        err = _truncate(stderr.decode("utf-8", errors="replace").strip())
        return ToolResult(
            success=proc.returncode == 0,
            output={"exit_code": proc.returncode, "stdout": out, "stderr": err, "cwd": str(cwd)},
            error=None if proc.returncode == 0 else (err or f"Código de saída {proc.returncode}"),
        )


class OpenTargetTool(JarvisTool):
    """Open a URL, file or folder with the default desktop application."""

    name = "open"
    description = (
        "Abrir um site/URL no navegador, um ficheiro com a app predefinida ou uma pasta no gestor "
        "de ficheiros (ex.: 'https://youtube.com', '~/Transferências/doc.pdf')."
    )
    parameters_hint = '{"target": "url-ou-caminho"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def describe_target(self, params: Dict[str, Any]) -> str:
        return str(params.get("target", "")).strip() or self.name

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        target = str(params.get("target", "")).strip()
        if not target:
            return ToolResult(success=False, error="Parâmetro 'target' é obrigatório.")
        if not self._policy.full_access:
            return ToolResult(success=False, error="Acesso total desativado (FULL_ACCESS=false).")
        if target.startswith("-"):
            return ToolResult(success=False, error="Alvo inválido.")
        scheme = re.match(r"^([a-z][a-z0-9+.-]*)://", target, re.IGNORECASE)
        if scheme and scheme.group(1).lower() not in ("http", "https", "file"):
            return ToolResult(success=False, error=f"Esquema '{scheme.group(1)}' não permitido.")
        if not has_graphical_session():
            return ToolResult(success=False, error="Sessão gráfica não detetada neste processo.")
        if not re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE):
            path = Path(target).expanduser()
            if not path.is_absolute():
                path = Path.home() / path
            if not path.exists():
                return ToolResult(success=False, error=f"Não encontrei '{path}'.")
            target = str(path)
        subprocess.Popen(
            ["xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return ToolResult(success=True, output={"opened": target})
