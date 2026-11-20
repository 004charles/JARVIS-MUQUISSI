"""Tests for Phase 10 desktop integration: Ubuntu launcher, autostart, and notifications."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import desktop as desktop_api
from app.desktop.service import DesktopService


@pytest.mark.asyncio
async def test_desktop_service_autostart_launcher_and_notify(tmp_path: Path) -> None:
    sent_cmds: list[list[str]] = []

    async def fake_runner(cmd: list[str]) -> bool:
        sent_cmds.append(cmd)
        return True

    svc = DesktopService(
        autostart_dir=tmp_path / "autostart",
        applications_dir=tmp_path / "applications",
        notify_runner=fake_runner,
    )

    assert svc.status()["autostart_enabled"] is False
    svc.set_autostart(True)
    assert svc.status()["autostart_enabled"] is True
    content = (tmp_path / "autostart" / "muquissi.desktop").read_text(encoding="utf-8")
    assert "Name=Muquissi" in content
    assert "start-desktop.sh" in content

    svc.set_autostart(False)
    assert svc.status()["autostart_enabled"] is False

    svc.install_desktop_entry()
    assert svc.status()["desktop_entry_installed"] is True

    ok = await svc.notify("Muquissi", "Alerta de teste", urgency="critical")
    assert ok is True
    assert len(sent_cmds) == 1
    assert "-u" in sent_cmds[0] and "critical" in sent_cmds[0]


def test_desktop_rest_endpoints_and_spa_app_route(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_runner(_cmd: list[str]) -> bool:
        return True

    isolated = DesktopService(
        autostart_dir=tmp_path / "autostart",
        applications_dir=tmp_path / "apps",
        notify_runner=fake_runner,
    )
    monkeypatch.setattr(desktop_api, "desktop_service", isolated)

    st = client.get("/api/v1/desktop/status")
    assert st.status_code == 200
    assert st.json()["autostart_enabled"] is False

    auto_on = client.put("/api/v1/desktop/autostart", json={"enabled": True})
    assert auto_on.status_code == 200
    assert auto_on.json()["autostart_enabled"] is True

    launcher = client.post("/api/v1/desktop/install-launcher")
    assert launcher.status_code == 200
    assert launcher.json()["desktop_entry_installed"] is True

    notif_toggle = client.put("/api/v1/desktop/notifications", json={"enabled": True})
    assert notif_toggle.status_code == 200
    assert notif_toggle.json()["desktop_notifications_enabled"] is True

    notify_resp = client.post(
        "/api/v1/desktop/notify",
        json={"title": "Muquissi", "message": "Fase 10 pronta.", "urgency": "normal"},
    )
    assert notify_resp.status_code == 200
    assert notify_resp.json()["sent"] is True

    app_resp = client.get("/app")
    assert app_resp.status_code in (200, 503)
