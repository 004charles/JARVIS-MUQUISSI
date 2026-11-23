"""Phase 10 Ubuntu desktop integration: native notifications, .desktop launcher, and autostart."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from app.core.config import PROJECT_ROOT
from app.core.logging import get_logger

logger = get_logger("desktop.service")

UrgencyLevel = Literal["low", "normal", "critical"]


class DesktopService:
    """Manages native Ubuntu desktop notifications, menu launcher, and autostart."""

    def __init__(
        self,
        project_root: Path | None = None,
        autostart_dir: Path | None = None,
        applications_dir: Path | None = None,
        notify_runner: Callable[[list[str]], Awaitable[bool]] | None = None,
    ) -> None:
        self.project_root = project_root or PROJECT_ROOT
        self.autostart_dir = autostart_dir or (Path.home() / ".config" / "autostart")
        self.applications_dir = applications_dir or (
            Path.home() / ".local" / "share" / "applications"
        )
        self.notifications_enabled: bool = True
        self._notify_runner = notify_runner

    @property
    def launch_script_path(self) -> Path:
        return self.project_root / "scripts" / "start-desktop.sh"

    @property
    def icon_path(self) -> Path:
        return self.project_root / "scripts" / "muquissi-icon.svg"

    @property
    def frontend_dist_index(self) -> Path:
        return self.project_root / "frontend" / "dist" / "index.html"

    @property
    def autostart_file_path(self) -> Path:
        return self.autostart_dir / "muquissi.desktop"

    @property
    def desktop_entry_path(self) -> Path:
        return self.applications_dir / "muquissi.desktop"

    def render_desktop_entry(self, hidden: bool = False) -> str:
        """Render a valid XDG `.desktop` entry pointing to the unified desktop launcher."""
        icon_val = str(self.icon_path) if self.icon_path.exists() else "utilities-terminal"
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=Arcanjo",
            "GenericName=Assistente Pessoal Inteligente",
            "Comment=Assistente Pessoal Inteligente com Voz, Visão e Agentes",
            f'Exec="{self.launch_script_path}"',
            f"Icon={icon_val}",
            "Terminal=false",
            "Categories=Utility;Office;",
            "StartupNotify=true",
        ]
        if hidden:
            lines.append("X-GNOME-Autostart-enabled=true")
        return "\n".join(lines) + "\n"

    def status(self) -> dict[str, object]:
        """Return Phase 10 desktop readiness and Ubuntu integration status."""
        return {
            "notify_send_available": bool(shutil.which("notify-send")),
            "desktop_notifications_enabled": self.notifications_enabled,
            "autostart_enabled": self.autostart_file_path.exists(),
            "autostart_path": str(self.autostart_file_path),
            "desktop_entry_installed": self.desktop_entry_path.exists(),
            "desktop_entry_path": str(self.desktop_entry_path),
            "frontend_dist_ready": self.frontend_dist_index.is_file(),
            "launch_script": str(self.launch_script_path),
        }

    def set_autostart(self, enabled: bool) -> dict[str, object]:
        """Enable or disable Ubuntu login autostart via `~/.config/autostart/muquissi.desktop`."""
        if enabled:
            self.autostart_dir.mkdir(parents=True, exist_ok=True)
            self.autostart_file_path.write_text(
                self.render_desktop_entry(hidden=True), encoding="utf-8"
            )
            logger.info("Autostart Ubuntu ativado em %s", self.autostart_file_path)
        else:
            self.autostart_file_path.unlink(missing_ok=True)
            logger.info("Autostart Ubuntu desativado.")
        return self.status()

    def install_desktop_entry(self) -> dict[str, object]:
        """Install Arcanjo shortcut in Ubuntu applications menu."""
        self.applications_dir.mkdir(parents=True, exist_ok=True)
        self.desktop_entry_path.write_text(
            self.render_desktop_entry(hidden=False), encoding="utf-8"
        )
        logger.info("Atalho desktop instalado em %s", self.desktop_entry_path)
        return self.status()

    async def notify(
        self,
        title: str,
        message: str,
        urgency: UrgencyLevel = "normal",
    ) -> bool:
        """Send a native Ubuntu notification via `notify-send` when enabled."""
        if not self.notifications_enabled:
            return False

        clean_title = title.strip()[:120] or "Arcanjo"
        clean_msg = message.strip()[:300]
        if not clean_msg:
            return False

        # Never trigger desktop popups during automated tests unless custom mock runner is supplied
        if "PYTEST_CURRENT_TEST" in os.environ and self._notify_runner is None:
            return False

        notify_bin = shutil.which("notify-send")
        if not notify_bin and self._notify_runner is None:
            return False

        icon_arg = str(self.icon_path) if self.icon_path.exists() else "dialog-information"
        cmd = [
            notify_bin or "notify-send",
            "-a",
            "Arcanjo",
            "-u",
            urgency,
            "-i",
            icon_arg,
            clean_title,
            clean_msg,
        ]

        if self._notify_runner is not None:
            return await self._notify_runner(cmd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await asyncio.wait_for(proc.wait(), timeout=3.0)
            return rc == 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao enviar notificação nativa Ubuntu: %s", exc)
            return False


desktop_service = DesktopService()
