"""Programming and Git inspection tools inside authorized directories (Level 1 Safe)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.security.permissions import PermissionLevel, SecurityPolicy, SecurityViolation
from app.tools.base import JarvisTool, ToolResult


class GitStatusTool(JarvisTool):
    """Inspect Git branch, working tree status, and recent commits in an authorized directory."""

    name = "git_status"
    description = "Consultar estado do Git e últimos commits num diretório autorizado."
    parameters_hint = '{"directory": "caminho-opcional"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_dir = str(params.get("directory") or (self._policy.allowed_directories[0] if self._policy.allowed_directories else "."))
        try:
            repo_dir = self._policy.validate_authorized_path(raw_dir)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_dir),
            "status",
            "--short",
            "--branch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return ToolResult(success=False, error=err or "Diretório não é um repositório Git.")

        log_proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_dir),
            "log",
            "-n",
            "5",
            "--oneline",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        log_out, _ = await asyncio.wait_for(log_proc.communicate(), timeout=5.0)

        return ToolResult(
            success=True,
            output={
                "directory": str(repo_dir),
                "status": stdout.decode("utf-8", errors="replace").strip(),
                "recent_commits": log_out.decode("utf-8", errors="replace").splitlines(),
            },
        )
