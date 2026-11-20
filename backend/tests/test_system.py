"""System telemetry, history, alerts, and persistent notifications tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.system.alerts import AlertConfig, SystemAlertEngine


def test_system_status_returns_real_metrics(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["cpu_cores"] >= 1
    assert 0.0 <= data["cpu_percent"] <= 100.0
    assert data["ram_total_gb"] > 0
    assert data["disk_total_gb"] > 0
    assert data["net_rx_kbps"] >= 0.0
    assert data["net_tx_kbps"] >= 0.0
    assert isinstance(data["network_connected"], bool)
    assert isinstance(data["top_processes"], list)


def test_system_history_and_alert_config_endpoints(client: TestClient) -> None:
    hist_resp = client.get("/api/v1/system/history")
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()["points"]) >= 1

    cfg_resp = client.get("/api/v1/system/alerts/config")
    assert cfg_resp.status_code == 200
    assert "cpu_threshold" in cfg_resp.json()

    put_resp = client.put(
        "/api/v1/system/alerts/config",
        json={
            "enabled": True,
            "cpu_threshold": 90.0,
            "ram_threshold": 88.0,
            "disk_threshold": 97.0,
            "temp_threshold": 85.0,
            "cooldown_seconds": 120,
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["cpu_threshold"] == 90.0


@pytest.mark.asyncio
async def test_alert_engine_creates_and_deduplicates_notifications(
    client: TestClient, db_session: Session
) -> None:
    engine = SystemAlertEngine()
    engine.update_config(
        db_session,
        AlertConfig(
            enabled=True,
            cpu_threshold=50.0,
            ram_threshold=90.0,
            disk_threshold=95.0,
            temp_threshold=85.0,
            cooldown_seconds=300,
        ),
    )

    high_snapshot = {
        "cpu_percent": 75.0,
        "ram_percent": 40.0,
        "ram_used_gb": 6.0,
        "ram_total_gb": 16.0,
        "disk_percent": 60.0,
        "disk_free_gb": 100.0,
        "temperature_celsius": 50.0,
    }

    created = await engine.evaluate(db_session, high_snapshot)
    assert len(created) == 1
    assert created[0].title == "CPU elevado"

    # Cooldown must prevent duplicate spam on immediate re-evaluation
    second = await engine.evaluate(db_session, high_snapshot)
    assert second == []

    notif_resp = client.get("/api/v1/notifications")
    assert notif_resp.status_code == 200
    data = notif_resp.json()
    assert data["unread_count"] == 1
    notif_id = data["items"][0]["id"]

    read_resp = client.post(f"/api/v1/notifications/{notif_id}/read")
    assert read_resp.status_code == 200
    assert client.get("/api/v1/notifications").json()["unread_count"] == 0
