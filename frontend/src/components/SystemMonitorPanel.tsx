import { Activity, Cpu, HardDrive, Network, Shield, Sliders } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "../services/api";
import type {
  AlertConfigData,
  SystemSnapshot,
  TelemetryHistoryPoint,
} from "../types/api";
import { ToolsSecurityPanel } from "./ToolsSecurityPanel";

interface SystemMonitorPanelProps {
  system: SystemSnapshot | null;
}

type SystemTab = "telemetry" | "processes" | "alerts" | "tools";

function SparkChart({
  title,
  valueLabel,
  values,
  color,
  maxValue = 100,
}: {
  title: string;
  valueLabel: string;
  values: number[];
  color: string;
  maxValue?: number;
}) {
  const safeMax = Math.max(1, maxValue, ...values);
  const points =
    values.length > 1
      ? values
          .map((v, i) => {
            const x = (i / (values.length - 1)) * 220;
            const y = 48 - (Math.min(safeMax, Math.max(0, v)) / safeMax) * 42;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(" ")
      : "0,44 220,44";

  return (
    <div className="rounded-xl border border-cyan-500/20 bg-slate-900/55 p-3">
      <div className="mb-2 flex items-center justify-between font-mono text-[11px]">
        <span className="text-slate-300">{title}</span>
        <span style={{ color }}>{valueLabel}</span>
      </div>
      <svg viewBox="0 0 220 52" className="h-12 w-full overflow-visible">
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
    </div>
  );
}

export function SystemMonitorPanel({ system }: SystemMonitorPanelProps) {
  const [tab, setTab] = useState<SystemTab>("telemetry");
  const [history, setHistory] = useState<TelemetryHistoryPoint[]>([]);
  const [alertCfg, setAlertCfg] = useState<AlertConfigData | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([apiClient.getSystemHistory(), apiClient.getAlertConfig()]).then(
      ([histRes, cfgRes]) => {
        setHistory(histRes.points);
        setAlertCfg(cfgRes);
      },
    );
  }, []);

  useEffect(() => {
    if (!system) return;
    setHistory((prev) => [
      ...prev.slice(-59),
      {
        timestamp: new Date().toISOString(),
        cpu_percent: system.cpu_percent,
        ram_percent: system.ram_percent,
        disk_percent: system.disk_percent,
        net_rx_kbps: system.net_rx_kbps ?? 0,
        net_tx_kbps: system.net_tx_kbps ?? 0,
        temperature_celsius: system.temperature_celsius,
      },
    ]);
  }, [system]);

  if (tab === "tools") {
    return (
      <div className="my-auto w-full max-w-3xl space-y-3">
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["telemetry", "Monitorização"],
              ["processes", "Processos"],
              ["alerts", "Alertas"],
              ["tools", "Ferramentas & Auditoria"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-lg border px-3 py-1 font-mono text-[11px] transition ${
                tab === id
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                  : "border-cyan-500/20 bg-slate-950/60 text-slate-300 hover:border-cyan-400/50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <ToolsSecurityPanel />
      </div>
    );
  }

  const handleSaveAlerts = async () => {
    if (!alertCfg) return;
    setSaving(true);
    setSaveNote(null);
    try {
      const updated = await apiClient.updateAlertConfig(alertCfg);
      setAlertCfg(updated);
      setSaveNote("Limiares de alerta guardados.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="my-auto w-full max-w-3xl space-y-4 rounded-2xl border border-cyan-500/25 bg-slate-950/70 p-5 backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/15 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyan-300" />
          <h2 className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
            Monitorização Avançada do Sistema
          </h2>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["telemetry", "Gráficos"],
              ["processes", "Processos"],
              ["alerts", "Alertas"],
              ["tools", "Ferramentas"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] transition ${
                tab === id
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                  : "border-cyan-500/20 bg-slate-900/60 text-slate-300 hover:border-cyan-400/50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "telemetry" && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <SparkChart
              title="CPU (%)"
              valueLabel={`${system?.cpu_percent ?? 0}%`}
              values={history.map((p) => p.cpu_percent)}
              color="#22d3ee"
            />
            <SparkChart
              title="Memória RAM (%)"
              valueLabel={`${system?.ram_percent ?? 0}% (${system?.ram_used_gb ?? 0}/${system?.ram_total_gb ?? 0} GB)`}
              values={history.map((p) => p.ram_percent)}
              color="#38bdf8"
            />
            <SparkChart
              title="Rede Download (KB/s)"
              valueLabel={`${system?.net_rx_kbps ?? 0} KB/s`}
              values={history.map((p) => p.net_rx_kbps)}
              color="#34d399"
              maxValue={50}
            />
            <SparkChart
              title="Rede Upload (KB/s)"
              valueLabel={`${system?.net_tx_kbps ?? 0} KB/s`}
              values={history.map((p) => p.net_tx_kbps)}
              color="#818cf8"
              maxValue={50}
            />
          </div>

          {system && (
            <div className="grid grid-cols-2 gap-2.5 text-xs sm:grid-cols-4">
              <div className="rounded-xl border border-cyan-500/15 bg-slate-900/50 p-2.5">
                <span className="flex items-center gap-1 text-[10px] text-slate-400">
                  <Cpu className="h-3 w-3 text-cyan-300" />
                  Núcleos
                </span>
                <p className="mt-1 font-mono text-cyan-200">{system.cpu_cores}</p>
              </div>
              <div className="rounded-xl border border-cyan-500/15 bg-slate-900/50 p-2.5">
                <span className="flex items-center gap-1 text-[10px] text-slate-400">
                  <HardDrive className="h-3 w-3 text-cyan-300" />
                  Disco (/)
                </span>
                <p className="mt-1 font-mono text-amber-200">
                  {system.disk_percent}% ({system.disk_free_gb} GB livres)
                </p>
              </div>
              <div className="rounded-xl border border-cyan-500/15 bg-slate-900/50 p-2.5">
                <span className="flex items-center gap-1 text-[10px] text-slate-400">
                  <Network className="h-3 w-3 text-cyan-300" />
                  Rede
                </span>
                <p className="mt-1 font-mono text-emerald-300">
                  {system.network_connected ? "Ligada" : "Desligada"}
                </p>
              </div>
              <div className="rounded-xl border border-cyan-500/15 bg-slate-900/50 p-2.5">
                <span className="flex items-center gap-1 text-[10px] text-slate-400">
                  <Shield className="h-3 w-3 text-cyan-300" />
                  Temperatura
                </span>
                <p className="mt-1 font-mono text-cyan-200">
                  {system.temperature_celsius !== null
                    ? `${system.temperature_celsius} °C`
                    : "N/D"}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "processes" && (
        <div className="max-h-72 overflow-y-auto rounded-xl border border-cyan-500/15 bg-slate-900/50">
          <table className="w-full text-left font-mono text-[11px]">
            <thead className="border-b border-cyan-500/15 text-[10px] uppercase text-cyan-300">
              <tr>
                <th className="px-3 py-2">PID</th>
                <th className="px-3 py-2">Processo</th>
                <th className="px-3 py-2">CPU %</th>
                <th className="px-3 py-2">RAM %</th>
                <th className="px-3 py-2">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cyan-500/10 text-slate-200">
              {(system?.top_processes ?? []).map((p) => (
                <tr key={p.pid} className="hover:bg-cyan-500/5">
                  <td className="px-3 py-1.5 text-slate-400">{p.pid}</td>
                  <td className="px-3 py-1.5">{p.name}</td>
                  <td className="px-3 py-1.5 text-cyan-300">{p.cpu_percent}%</td>
                  <td className="px-3 py-1.5 text-sky-300">{p.memory_percent}%</td>
                  <td className="px-3 py-1.5 text-slate-400">{p.status || "running"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "alerts" && alertCfg && (
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between rounded-xl border border-cyan-500/15 bg-slate-900/55 px-3 py-2">
            <span className="flex items-center gap-2 text-slate-200">
              <Sliders className="h-4 w-4 text-cyan-300" />
              Monitorização automática de alertas
            </span>
            <button
              type="button"
              onClick={() => setAlertCfg({ ...alertCfg, enabled: !alertCfg.enabled })}
              className={`rounded-lg border px-3 py-1 font-mono text-[11px] ${
                alertCfg.enabled
                  ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
                  : "border-slate-600 bg-slate-800 text-slate-300"
              }`}
            >
              {alertCfg.enabled ? "ATIVOS" : "DESATIVADOS"}
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="space-y-1">
              <span className="block font-mono text-[10px] text-slate-400">CPU (%)</span>
              <input
                type="number"
                value={alertCfg.cpu_threshold}
                onChange={(e) =>
                  setAlertCfg({ ...alertCfg, cpu_threshold: Number(e.target.value) })
                }
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-2.5 py-1.5 font-mono text-xs text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="block font-mono text-[10px] text-slate-400">RAM (%)</span>
              <input
                type="number"
                value={alertCfg.ram_threshold}
                onChange={(e) =>
                  setAlertCfg({ ...alertCfg, ram_threshold: Number(e.target.value) })
                }
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-2.5 py-1.5 font-mono text-xs text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="block font-mono text-[10px] text-slate-400">Disco (%)</span>
              <input
                type="number"
                value={alertCfg.disk_threshold}
                onChange={(e) =>
                  setAlertCfg({ ...alertCfg, disk_threshold: Number(e.target.value) })
                }
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-2.5 py-1.5 font-mono text-xs text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="block font-mono text-[10px] text-slate-400">Temp (°C)</span>
              <input
                type="number"
                value={alertCfg.temp_threshold}
                onChange={(e) =>
                  setAlertCfg({ ...alertCfg, temp_threshold: Number(e.target.value) })
                }
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-2.5 py-1.5 font-mono text-xs text-slate-100"
              />
            </label>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-[11px] text-emerald-300">{saveNote || ""}</span>
            <button
              type="button"
              disabled={saving}
              onClick={() => void handleSaveAlerts()}
              className="rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-4 py-1.5 font-mono text-xs text-cyan-100 hover:bg-cyan-500/30"
            >
              {saving ? "A guardar..." : "Guardar Alertas"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
