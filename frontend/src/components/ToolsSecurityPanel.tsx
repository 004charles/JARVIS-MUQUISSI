import { FolderLock, RefreshCw, Shield, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "../services/api";
import type { ActionLogEntry, ToolsListResponse } from "../types/api";

export function ToolsSecurityPanel() {
  const [toolsData, setToolsData] = useState<ToolsListResponse | null>(null);
  const [logs, setLogs] = useState<ActionLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [toolsRes, logsRes] = await Promise.all([
        apiClient.getTools(),
        apiClient.getActionLogs(25),
      ]);
      setToolsData(toolsRes);
      setLogs(logsRes);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  return (
    <div className="my-auto w-full max-w-3xl space-y-4 rounded-2xl border border-cyan-500/25 bg-slate-950/70 p-5 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-cyan-500/15 pb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-cyan-300" />
          <h2 className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
            Ferramentas, Permissões & Auditoria
          </h2>
        </div>
        <button
          type="button"
          onClick={() => void loadData()}
          className="flex items-center gap-1.5 rounded-lg border border-cyan-500/25 bg-slate-900/70 px-2.5 py-1 font-mono text-[10px] text-cyan-200 hover:border-cyan-400/60"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>

      {toolsData && (
        <>
          <div className="rounded-xl border border-cyan-500/15 bg-slate-900/55 p-3 text-xs">
            <p className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-cyan-300">
              <FolderLock className="h-3.5 w-3.5" />
              Diretórios Autorizados
            </p>
            <div className="flex flex-wrap gap-1.5">
              {toolsData.allowed_directories.map((dir) => (
                <code
                  key={dir}
                  className="rounded-md border border-cyan-500/20 bg-slate-950/80 px-2 py-0.5 text-[11px] text-slate-200"
                >
                  {dir}
                </code>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-cyan-300">
              <TerminalSquare className="h-3.5 w-3.5" />
              Ferramentas Registadas ({toolsData.tools.length})
            </p>
            <div className="grid max-h-40 grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {toolsData.tools.map((tool) => (
                <div
                  key={tool.name}
                  className="rounded-xl border border-cyan-500/15 bg-slate-900/50 px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-cyan-200">{tool.name}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${
                        tool.permission_level === 1
                          ? "bg-emerald-500/15 text-emerald-300"
                          : "bg-amber-500/15 text-amber-300"
                      }`}
                    >
                      Nível {tool.permission_level}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">{tool.description}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-cyan-300">
          Histórico de Auditoria (`action_logs`)
        </p>
        <div className="max-h-36 space-y-1.5 overflow-y-auto pr-1 text-[11px]">
          {logs.length === 0 ? (
            <p className="text-slate-400">Nenhuma ação registada ainda.</p>
          ) : (
            logs.map((log) => (
              <div
                key={log.id}
                className="flex items-center justify-between rounded-lg border border-cyan-500/10 bg-slate-900/45 px-3 py-1.5 font-mono"
              >
                <div className="min-w-0 truncate pr-3">
                  <span className="text-cyan-200">{log.action_type}</span>{" "}
                  <span className="text-slate-400">· {log.target}</span>
                </div>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${
                    log.status === "executed"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : log.status === "awaiting_confirmation"
                        ? "bg-amber-500/15 text-amber-300"
                        : "bg-rose-500/15 text-rose-300"
                  }`}
                >
                  {log.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
