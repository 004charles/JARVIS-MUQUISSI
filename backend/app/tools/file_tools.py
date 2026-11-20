"""Authorized filesystem inspection and controlled creation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.security.permissions import PermissionLevel, SecurityPolicy, SecurityViolation
from app.tools.base import JarvisTool, ToolResult

_IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist"}
_MAX_READ_BYTES = 16 * 1024


class ListFilesTool(JarvisTool):
    """List files and folders inside an authorized directory (Level 1 Safe)."""

    name = "list_files"
    description = "Listar ficheiros e pastas dentro de um diretório autorizado."
    parameters_hint = '{"directory": "caminho-opcional"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_dir = str(params.get("directory") or (self._policy.allowed_directories[0] if self._policy.allowed_directories else "."))
        try:
            target_dir = self._policy.validate_authorized_path(raw_dir)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        if not target_dir.is_dir():
            return ToolResult(success=False, error=f"'{target_dir}' não é um diretório.")

        entries: List[Dict[str, object]] = []
        for child in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name in _IGNORED_DIRS or self._policy.is_sensitive_path(child):
                continue
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )
            if len(entries) >= 80:
                break

        return ToolResult(
            success=True,
            output={"directory": str(target_dir), "entries": entries},
        )


class SearchFilesTool(JarvisTool):
    """Search files by name inside authorized directories (Level 1 Safe)."""

    name = "search_files"
    description = "Pesquisar ficheiros por nome dentro dos diretórios autorizados."
    parameters_hint = '{"query": "texto-ou-extensao", "directory": "caminho-opcional"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        query = str(params.get("query", "")).strip().lower()
        if not query:
            return ToolResult(success=False, error="Parâmetro 'query' é obrigatório.")

        raw_dir = str(params.get("directory") or (self._policy.allowed_directories[0] if self._policy.allowed_directories else "."))
        try:
            root = self._policy.validate_authorized_path(raw_dir)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        matches: List[str] = []
        for item in root.rglob("*"):
            if any(part in _IGNORED_DIRS for part in item.parts):
                continue
            if self._policy.is_sensitive_path(item):
                continue
            if query in item.name.lower():
                matches.append(str(item.relative_to(root)))
                if len(matches) >= 40:
                    break

        return ToolResult(
            success=True,
            output={"directory": str(root), "query": query, "matches": matches},
        )


class ReadFileTool(JarvisTool):
    """Read an authorized non-sensitive text file (Level 1 Safe)."""

    name = "read_file"
    description = "Ler o conteúdo de um ficheiro de texto ou código autorizado."
    parameters_hint = '{"path": "caminho-do-ficheiro"}'
    permission_level = PermissionLevel.SAFE

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            return ToolResult(success=False, error="Parâmetro 'path' é obrigatório.")

        try:
            target = self._policy.validate_authorized_path(raw_path)
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        if not target.is_file():
            return ToolResult(success=False, error=f"'{target}' não é um ficheiro.")

        raw = target.read_bytes()
        truncated = len(raw) > _MAX_READ_BYTES
        text = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
        return ToolResult(
            success=True,
            output={"path": str(target), "content": text, "truncated": truncated},
        )


class CreateFileTool(JarvisTool):
    """Create a file inside an authorized directory (Level 2 Requires Confirmation)."""

    name = "create_file"
    description = "Criar um ficheiro dentro de um diretório autorizado (requer confirmação)."
    parameters_hint = '{"path": "caminho-do-ficheiro", "content": "conteudo"}'
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED

    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raw_path = str(params.get("path", "")).strip()
        content = str(params.get("content", ""))
        if not raw_path:
            return ToolResult(success=False, error="Parâmetro 'path' é obrigatório.")

        try:
            target: Path = self._policy.validate_authorized_path(
                raw_path, allow_nonexistent=True
            )
        except SecurityViolation as exc:
            return ToolResult(success=False, error=exc.reason)

        if target.exists():
            return ToolResult(
                success=False,
                error=f"O ficheiro '{target.name}' já existe; não será sobrescrito sem edição explícita.",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(
            success=True,
            output={"path": str(target), "bytes_written": len(content.encode("utf-8"))},
        )
