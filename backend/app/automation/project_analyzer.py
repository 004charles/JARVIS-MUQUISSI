"""Non-destructive project analyzer for authorized local directories."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from app.security.permissions import SecurityPolicy, SecurityViolation

_IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}


async def _run_git(repo_dir: Path, args: list[str]) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_dir),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return proc.returncode or 0, stdout.decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return 1, ""


def _detect_technologies_and_deps(root: Path) -> tuple[List[str], List[str]]:
    techs: set[str] = set()
    deps: List[str] = []

    if (root / "manage.py").exists():
        techs.add("Django")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "backend" / "requirements.txt").exists():
        techs.add("Python")
    if (root / "package.json").exists() or (root / "frontend" / "package.json").exists():
        techs.add("Node.js / JavaScript")
    if (root / "Cargo.toml").exists():
        techs.add("Rust")
    if (root / "pubspec.yaml").exists():
        techs.add("Flutter / Dart")

    for req_file in (root / "requirements.txt", root / "backend" / "requirements.txt"):
        if req_file.is_file():
            for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    pkg = clean.split("==")[0].split(">=")[0].split("<")[0].strip()
                    if pkg:
                        deps.append(pkg)
                    if "fastapi" in clean.lower():
                        techs.add("FastAPI")
                    if "django" in clean.lower():
                        techs.add("Django")
                    if "sqlalchemy" in clean.lower():
                        techs.add("SQLAlchemy")

    for pkg_file in (root / "package.json", root / "frontend" / "package.json"):
        if pkg_file.is_file():
            try:
                data = json.loads(pkg_file.read_text(encoding="utf-8"))
                all_js = {
                    **(data.get("dependencies") or {}),
                    **(data.get("devDependencies") or {}),
                }
                deps.extend(list(all_js.keys())[:25])
                if "react" in all_js:
                    techs.add("React")
                if "typescript" in all_js:
                    techs.add("TypeScript")
                if "vite" in all_js:
                    techs.add("Vite")
                if "tailwindcss" in all_js:
                    techs.add("Tailwind CSS")
            except json.JSONDecodeError:
                pass

    return sorted(techs), deps[:40]


async def analyze_project_directory(
    directory: str, policy: SecurityPolicy
) -> Dict[str, Any]:
    """Inspect structure, stack, dependencies, Git, and issues without modifying files."""
    try:
        root = policy.validate_authorized_path(directory)
    except SecurityViolation:
        raise

    if not root.is_dir():
        raise ValueError(f"'{root}' não é um diretório válido.")

    top_level = [
        {
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
        }
        for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        if item.name not in _IGNORED_DIRS and not policy.is_sensitive_path(item)
    ][:40]

    ext_counts: Counter[str] = Counter()
    total_files = 0
    for item in root.rglob("*"):
        if any(part in _IGNORED_DIRS for part in item.parts):
            continue
        if item.is_file() and not policy.is_sensitive_path(item):
            total_files += 1
            ext = item.suffix.lower() or "(sem extensão)"
            ext_counts[ext] += 1
            if total_files >= 1500:
                break

    technologies, dependencies = _detect_technologies_and_deps(root)

    git_rc, git_status = await _run_git(root, ["status", "--short", "--branch"])
    _, git_log = await _run_git(root, ["log", "-n", "5", "--oneline"])

    issues: List[str] = []
    recommendations: List[str] = []

    if git_rc != 0:
        issues.append("Repositório Git não inicializado neste diretório.")
        recommendations.append("Inicializar controlo de versão com `git init`.")
    elif "\n" in git_status:
        issues.append("Existem alterações não commitadas no working tree.")
        recommendations.append("Rever `git status` e criar commits organizados.")

    if (root / ".env.example").exists() and not (root / ".env").exists():
        issues.append("Ficheiro `.env` ausente (existe `.env.example`).")
        recommendations.append("Copiar `.env.example` para `.env` antes de executar serviços.")

    if not (root / "README.md").exists():
        issues.append("Documentação `README.md` ausente na raiz do projeto.")
        recommendations.append("Adicionar um `README.md` com instruções de arranque e testes.")

    if not issues:
        recommendations.append("Estrutura saudável e pronta para desenvolvimento contínuo.")

    return {
        "directory": str(root),
        "total_files_scanned": total_files,
        "top_extensions": dict(ext_counts.most_common(8)),
        "top_level": top_level,
        "technologies": technologies,
        "dependencies": dependencies,
        "git": {
            "initialized": git_rc == 0,
            "status": git_status,
            "recent_commits": git_log.splitlines() if git_log else [],
        },
        "issues": issues,
        "recommendations": recommendations,
    }
