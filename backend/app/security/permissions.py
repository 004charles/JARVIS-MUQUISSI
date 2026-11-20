"""Security policy, path/app/command validation, and Level 2 approval queue."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.core.config import Settings, get_settings


class PermissionLevel(IntEnum):
    """Three-tier action safety levels required by J.A.R.V.I.S. security policy."""

    SAFE = 1  # Read-only queries, authorized status, allowlisted app launch
    CONFIRMATION_REQUIRED = 2  # File creation/edits, scripts, closing apps, config
    RESTRICTED = 3  # Destructive ops, sudo, firewall, credentials, external exfil


class SecurityViolation(Exception):
    """Raised when an action violates security rules or accesses restricted resources."""

    def __init__(self, reason: str, level: PermissionLevel = PermissionLevel.RESTRICTED) -> None:
        super().__init__(reason)
        self.reason = reason
        self.level = level


ALLOWED_DESKTOP_APPS: Dict[str, List[str]] = {
    "vscode": ["code"],
    "code": ["code"],
    "terminal": ["gnome-terminal", "x-terminal-emulator", "konsole", "xfce4-terminal"],
    "files": ["nautilus", "thunar", "dolphin"],
    "ficheiros": ["nautilus", "thunar", "dolphin"],
    "firefox": ["firefox"],
    "chrome": ["google-chrome", "chromium", "chromium-browser"],
    "calculator": ["gnome-calculator", "kcalc"],
    "calculadora": ["gnome-calculator", "kcalc"],
    "editor": ["gedit", "gnome-text-editor", "kate"],
}

_SENSITIVE_NAME_PATTERNS = (
    ".env",
    ".ssh",
    ".gnupg",
    ".aws",
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
    "shadow",
    "passwd",
)
_SENSITIVE_EXTENSIONS = (".pem", ".key", ".p12", ".pfx", ".kdbx")
_RESTRICTED_COMMAND_PATTERNS = (
    r"\bsudo\b",
    r"\bsu\b",
    r"\brm\s+-rf\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+777\b",
    r"\bchown\b",
    r"\bufw\b",
    r"\biptables\b",
    r"\bshutdown\b",
    r"\breboot\b",
)
_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.@-]{1,64}$")


@dataclass
class PendingApproval:
    """Level 2 action awaiting explicit user confirmation."""

    id: str
    tool_name: str
    target: str
    params: Dict[str, Any]
    description: str
    permission_level: PermissionLevel = PermissionLevel.CONFIRMATION_REQUIRED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=10)
    )


class SecurityPolicy:
    """Enforces directory boundaries, credential protection, and approval workflow."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pending: Dict[str, PendingApproval] = {}

    @property
    def allowed_directories(self) -> List[Path]:
        """Return resolved authorized root directories."""
        return self.settings.allowed_directories_list

    def is_sensitive_path(self, path: Path) -> bool:
        """Detect credential, key, or system-auth files that must never be exposed."""
        parts_lower = [part.lower() for part in path.parts]
        name_lower = path.name.lower()
        if any(pat in parts_lower or name_lower == pat or name_lower.startswith(f"{pat}.") for pat in _SENSITIVE_NAME_PATTERNS):
            return True
        if name_lower.endswith(_SENSITIVE_EXTENSIONS):
            return True
        return False

    def validate_authorized_path(self, raw_path: str, allow_nonexistent: bool = False) -> Path:
        """Resolve a user/AI path and verify it stays inside authorized directories."""
        candidate_raw = Path(raw_path).expanduser()
        if not candidate_raw.is_absolute() and self.allowed_directories:
            candidate_raw = self.allowed_directories[0] / candidate_raw

        resolved = candidate_raw.resolve()
        if not any(
            resolved == root or resolved.is_relative_to(root)
            for root in self.allowed_directories
        ):
            raise SecurityViolation(
                f"Acesso negado: '{resolved}' está fora dos diretórios autorizados.",
                level=PermissionLevel.RESTRICTED,
            )

        if self.is_sensitive_path(resolved):
            raise SecurityViolation(
                f"Acesso bloqueado por segurança: '{resolved.name}' é um ficheiro sensível/credencial.",
                level=PermissionLevel.RESTRICTED,
            )

        if not allow_nonexistent and not resolved.exists():
            raise SecurityViolation(
                f"Caminho não encontrado: '{resolved}'.",
                level=PermissionLevel.SAFE,
            )
        return resolved

    def validate_service_name(self, service: str) -> str:
        """Validate a systemd service name."""
        clean = service.strip()
        if not _SERVICE_NAME_RE.match(clean):
            raise SecurityViolation(
                f"Nome de serviço inválido: '{service}'.",
                level=PermissionLevel.RESTRICTED,
            )
        return clean

    def validate_text_command_safety(self, command_text: str) -> None:
        """Reject Level 3 destructive or privileged shell patterns."""
        lowered = command_text.lower()
        for pattern in _RESTRICTED_COMMAND_PATTERNS:
            if re.search(pattern, lowered):
                raise SecurityViolation(
                    "Operação bloqueada pelo Nível 3 de segurança (comando privilegiado ou destrutivo).",
                    level=PermissionLevel.RESTRICTED,
                )

    def resolve_allowed_app(self, app_name: str) -> List[str]:
        """Map a friendly application name to allowlisted Ubuntu binary candidates."""
        key = app_name.strip().lower()
        if key not in ALLOWED_DESKTOP_APPS:
            raise SecurityViolation(
                f"Aplicação '{app_name}' não consta na lista de aplicações autorizadas.",
                level=PermissionLevel.RESTRICTED,
            )
        return ALLOWED_DESKTOP_APPS[key]

    def create_pending_approval(
        self,
        tool_name: str,
        target: str,
        params: Dict[str, Any],
        description: str,
    ) -> PendingApproval:
        """Register a Level 2 action waiting for explicit user approval."""
        self._prune_expired()
        approval = PendingApproval(
            id=uuid.uuid4().hex[:12],
            tool_name=tool_name,
            target=target,
            params=params,
            description=description,
        )
        self._pending[approval.id] = approval
        return approval

    def pop_pending_approval(self, approval_id: str) -> PendingApproval | None:
        """Retrieve and remove a non-expired pending approval."""
        self._prune_expired()
        return self._pending.pop(approval_id, None)

    def list_pending_approvals(self) -> List[PendingApproval]:
        """List currently active pending approvals."""
        self._prune_expired()
        return list(self._pending.values())

    def _prune_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired: Iterable[str] = [
            key for key, item in self._pending.items() if item.expires_at <= now
        ]
        for key in expired:
            self._pending.pop(key, None)


security_policy = SecurityPolicy()
