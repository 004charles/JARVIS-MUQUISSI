"""Configurable system threshold alerts and persistent notifications."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping

from sqlalchemy.orm import Session

from app.core.events import EventType, event_bus
from app.database.models import NotificationEntry, SettingEntry
from app.desktop import desktop_service

SETTING_ALERTS_KEY = "system.alerts.config"


@dataclass
class AlertConfig:
    """Configurable system alert thresholds."""

    enabled: bool = True
    cpu_threshold: float = 88.0
    ram_threshold: float = 85.0
    disk_threshold: float = 95.0
    temp_threshold: float = 82.0
    cooldown_seconds: int = 300


class SystemAlertEngine:
    """Evaluates telemetry snapshots and emits deduplicated persistent alerts."""

    def __init__(self) -> None:
        self._last_fired: Dict[str, float] = {}

    def get_config(self, db: Session) -> AlertConfig:
        """Load persisted alert configuration or return defaults."""
        entry = db.get(SettingEntry, SETTING_ALERTS_KEY)
        if entry is None:
            return AlertConfig()
        try:
            raw = json.loads(entry.value)
            return AlertConfig(
                enabled=bool(raw.get("enabled", True)),
                cpu_threshold=float(raw.get("cpu_threshold", 88.0)),
                ram_threshold=float(raw.get("ram_threshold", 85.0)),
                disk_threshold=float(raw.get("disk_threshold", 95.0)),
                temp_threshold=float(raw.get("temp_threshold", 82.0)),
                cooldown_seconds=int(raw.get("cooldown_seconds", 300)),
            )
        except Exception:  # noqa: BLE001
            return AlertConfig()

    def update_config(self, db: Session, cfg: AlertConfig) -> AlertConfig:
        """Persist updated alert thresholds in SQLite."""
        serialized = json.dumps(asdict(cfg))
        entry = db.get(SettingEntry, SETTING_ALERTS_KEY)
        if entry is None:
            db.add(SettingEntry(key=SETTING_ALERTS_KEY, value=serialized, category="system"))
        else:
            entry.value = serialized
        db.commit()
        return cfg

    async def evaluate(
        self, db: Session, snapshot: Mapping[str, Any]
    ) -> List[NotificationEntry]:
        """Check snapshot metrics against thresholds and persist new notifications."""
        cfg = self.get_config(db)
        if not cfg.enabled:
            return []

        now = time.monotonic()
        checks: list[tuple[str, float | None, float, str, str, str]] = [
            (
                "cpu_high",
                snapshot.get("cpu_percent"),
                cfg.cpu_threshold,
                "warning",
                "CPU elevado",
                f"Utilização do processador atingiu {snapshot.get('cpu_percent')}% (limite {cfg.cpu_threshold}%).",
            ),
            (
                "ram_high",
                snapshot.get("ram_percent"),
                cfg.ram_threshold,
                "warning",
                "Memória RAM elevada",
                f"Memória RAM em {snapshot.get('ram_percent')}% ({snapshot.get('ram_used_gb')}/{snapshot.get('ram_total_gb')} GB).",
            ),
            (
                "disk_high",
                snapshot.get("disk_percent"),
                cfg.disk_threshold,
                "critical",
                "Disco quase cheio",
                f"O disco principal (/) está em {snapshot.get('disk_percent')}% ({snapshot.get('disk_free_gb')} GB livres).",
            ),
            (
                "temp_high",
                snapshot.get("temperature_celsius"),
                cfg.temp_threshold,
                "critical",
                "Temperatura elevada",
                f"Temperatura atingiu {snapshot.get('temperature_celsius')} °C (limite {cfg.temp_threshold} °C).",
            ),
        ]

        created: List[NotificationEntry] = []
        for key, value, threshold, severity, title, message in checks:
            if value is None or float(value) < threshold:
                continue
            last_time = self._last_fired.get(key)
            if last_time is not None and (now - last_time) < cfg.cooldown_seconds:
                continue
            self._last_fired[key] = now

            entry = NotificationEntry(
                title=title,
                message=message,
                severity=severity,
                source="system_monitor",
                read=False,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            created.append(entry)

            await event_bus.emit(
                EventType.NOTIFICATION_CREATED.value,
                {
                    "id": entry.id,
                    "title": entry.title,
                    "message": entry.message,
                    "severity": entry.severity,
                    "source": entry.source,
                    "read": entry.read,
                    "created_at": entry.created_at.isoformat(),
                },
            )
            urgency = "critical" if entry.severity == "critical" else "normal"
            await desktop_service.notify(entry.title, entry.message, urgency=urgency)

        return created


alert_engine = SystemAlertEngine()
