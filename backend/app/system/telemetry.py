"""Real-time Ubuntu/Linux system telemetry and rolling history via psutil."""

from __future__ import annotations

import platform
import socket
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List

import psutil

_prev_net_bytes: tuple[float, int, int] | None = None
_history_buffer: Deque[Dict[str, Any]] = deque(maxlen=60)


def _measure_network_kbps() -> tuple[float, float]:
    """Compute real network receive/transmit throughput in KB/s from counter deltas."""
    global _prev_net_bytes
    try:
        counters = psutil.net_io_counters()
        now = time.monotonic()
        if counters is None:
            return 0.0, 0.0
        rx_total = int(counters.bytes_recv)
        tx_total = int(counters.bytes_sent)
        if _prev_net_bytes is None:
            _prev_net_bytes = (now, rx_total, tx_total)
            return 0.0, 0.0
        prev_t, prev_rx, prev_tx = _prev_net_bytes
        dt = max(0.2, now - prev_t)
        rx_kbps = max(0.0, (rx_total - prev_rx) / 1024.0 / dt)
        tx_kbps = max(0.0, (tx_total - prev_tx) / 1024.0 / dt)
        _prev_net_bytes = (now, rx_total, tx_total)
        return round(rx_kbps, 1), round(tx_kbps, 1)
    except Exception:  # noqa: BLE001
        return 0.0, 0.0


def get_system_snapshot(record_history: bool = False) -> Dict[str, Any]:
    """Collect real local hardware, network throughput, and OS telemetry."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=None)
    boot_time = psutil.boot_time()
    uptime_seconds = max(0, int(time.time() - boot_time))
    net_rx_kbps, net_tx_kbps = _measure_network_kbps()

    temperature_celsius: float | None = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    temperature_celsius = round(entries[0].current, 1)
                    break
    except Exception:  # noqa: BLE001
        temperature_celsius = None

    battery_percent: float | None = None
    battery_plugged: bool | None = None
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            battery_percent = round(battery.percent, 1)
            battery_plugged = bool(battery.power_plugged)
    except Exception:  # noqa: BLE001
        battery_percent = None

    net_connected = False
    try:
        stats = psutil.net_if_stats()
        net_connected = any(
            iface != "lo" and info.isup for iface, info in stats.items()
        )
    except Exception:  # noqa: BLE001
        net_connected = False

    top_processes: List[Dict[str, Any]] = []
    try:
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            info = proc.info
            if info.get("name"):
                procs.append(
                    {
                        "pid": info["pid"],
                        "name": str(info["name"])[:30],
                        "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 1),
                        "memory_percent": round(float(info.get("memory_percent") or 0.0), 1),
                        "status": str(info.get("status") or ""),
                    }
                )
        procs.sort(key=lambda item: (item["cpu_percent"], item["memory_percent"]), reverse=True)
        top_processes = procs[:10]
    except Exception:  # noqa: BLE001
        top_processes = []

    snapshot = {
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "cpu_percent": round(cpu_percent, 1),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_available_gb": round(mem.available / (1024**3), 2),
        "ram_percent": round(mem.percent, 1),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "net_rx_kbps": net_rx_kbps,
        "net_tx_kbps": net_tx_kbps,
        "uptime_seconds": uptime_seconds,
        "temperature_celsius": temperature_celsius,
        "battery_percent": battery_percent,
        "battery_plugged": battery_plugged,
        "network_connected": net_connected,
        "top_processes": top_processes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if record_history:
        _history_buffer.append(
            {
                "timestamp": snapshot["timestamp"],
                "cpu_percent": snapshot["cpu_percent"],
                "ram_percent": snapshot["ram_percent"],
                "disk_percent": snapshot["disk_percent"],
                "net_rx_kbps": net_rx_kbps,
                "net_tx_kbps": net_tx_kbps,
                "temperature_celsius": temperature_celsius,
            }
        )

    return snapshot


def get_system_history() -> List[Dict[str, Any]]:
    """Return recent rolling telemetry points."""
    if not _history_buffer:
        get_system_snapshot(record_history=True)
    return list(_history_buffer)
