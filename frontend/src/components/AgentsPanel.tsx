import { Bot, CheckCircle2, Code2, Cpu, FolderKanban, Globe, Play, RefreshCw, Volume2, Workflow } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiClient } from "../services/api";
import type { AgentProfileItem, AgentRunItem, AgentType } from "../types/api";

interface AgentsPanelProps {
  latestAgentRun?: AgentRunItem | null;
  onSpeakSummary?: (text: string) => void;
}

const AGENT_ICONS: Record<AgentType, typeof Bot> = {
  coding: Code2,
  system: Cpu,
  research: Globe,
  automation: Workflow,
  project: FolderKanban,
};

export function AgentsPanel({ latestAgentRun, onSpeakSummary }: AgentsPanelProps) {
  const [profiles, setProfiles] = useState<AgentProfileItem[]>([]);
  const [runs, setRuns] = useState<AgentRunItem[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentType | "auto">("auto");
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);
  const [activeRun, setActiveRun] = useState<AgentRunItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [agentsRes, runsRes] = await Promise.all([
        apiClient.getAgents(),
        apiClient.getAgentRuns(12),
      ]);
      setProfiles(agentsRes.agents);
      setRuns(runsRes.runs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar agentes.");
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (!latestAgentRun) return;
    setActiveRun(latestAgentRun);
    setRuns((prev) => [latestAgentRun, ...prev.filter((r) => r.id !== latestAgentRun.id)].slice(0, 12));
  }, [latestAgentRun]);

  const handleLaunchMission = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed || running) return;

    setRunning(true);
    setError(null);
    try {
      const res = await apiClient.runAgent(
        trimmed,
        selectedAgent === "auto" ? undefined : selectedAgent,
      );
      setActiveRun(res);
      setRuns((prev) => [res, ...prev.filter((r) => r.id !== res.id)].slice(0, 12));
      setGoal("");
      if (res.summary && onSpeakSummary) {
        onSpeakSummary(res.summary);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao executar missão do agente.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">Agentes Especializados (Fase 9)</h3>
          <p className="text-xs text-slate-400">
            Missões autónomas multi-passo com controlo de segurança (Níveis 1–3).
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadData()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-slate-200 transition hover:bg-white/10"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Atualizar
        </button>
      </div>

      {/* Specialized Agent Selector */}
      <div className="grid gap-2 sm:grid-cols-3">
        <button
          type="button"
          onClick={() => setSelectedAgent("auto")}
          className={`rounded-xl border p-3 text-left transition ${
            selectedAgent === "auto"
              ? "border-cyan-400 bg-cyan-500/15 text-cyan-100"
              : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
          }`}
        >
          <div className="flex items-center gap-1.5 text-xs font-semibold">
            <Bot className="h-3.5 w-3.5 text-cyan-300" />
            Roteamento Automático
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            O Muquissi escolhe automaticamente o agente ideal para a missão.
          </p>
        </button>

        {profiles.map((agent) => {
          const Icon = AGENT_ICONS[agent.id] ?? Bot;
          return (
            <button
              key={agent.id}
              type="button"
              onClick={() => setSelectedAgent(agent.id)}
              className={`rounded-xl border p-3 text-left transition ${
                selectedAgent === agent.id
                  ? "border-cyan-400 bg-cyan-500/15 text-cyan-100"
                  : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              <div className="flex items-center justify-between gap-1 text-xs font-semibold">
                <span className="flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5 text-sky-300" />
                  {agent.name}
                </span>
                <span className="font-mono text-[10px] text-slate-400">
                  {agent.allowed_tools.length} tools
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">{agent.description}</p>
            </button>
          );
        })}
      </div>

      {/* Mission Form */}
      <form onSubmit={(e) => void handleLaunchMission(e)} className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Descreve a missão (ex.: Verifica os testes do backend ou analisa uso de RAM)..."
          className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white placeholder:text-slate-400 focus:border-cyan-400/60 focus:outline-none"
        />
        <button
          type="submit"
          disabled={running || !goal.trim()}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {running ? "A executar..." : "Executar Missão"}
        </button>
      </form>

      {error && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </div>
      )}

      {/* Latest / Active Run Report */}
      {activeRun && (
        <div className="space-y-2 rounded-2xl border border-emerald-400/25 bg-emerald-500/10 p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-200">
              <CheckCircle2 className="h-4 w-4" />
              <span>{activeRun.agent_name}</span>
              <span className="rounded-full bg-white/10 px-2 py-0.5 font-mono text-[10px] uppercase">
                {activeRun.status}
              </span>
            </div>
            {activeRun.summary && onSpeakSummary && (
              <button
                type="button"
                onClick={() => onSpeakSummary(activeRun.summary)}
                className="inline-flex items-center gap-1 rounded-lg border border-emerald-400/30 bg-emerald-500/15 px-2.5 py-1 text-[11px] text-emerald-100 hover:bg-emerald-500/25"
              >
                <Volume2 className="h-3.5 w-3.5" />
                Ouvir Resumo
              </button>
            )}
          </div>
          {activeRun.steps.length > 0 && (
            <div className="space-y-1 border-t border-white/10 pt-2 font-mono text-[11px] text-slate-300">
              {activeRun.steps.map((s) => (
                <div key={`${activeRun.id}-${s.step}`} className="flex gap-2">
                  <span className="text-cyan-300">#{s.step}</span>
                  <span className="text-slate-100">{s.action}</span>
                  <span className="text-slate-400">({s.status})</span>
                  {s.detail && <span className="truncate text-slate-400">— {s.detail}</span>}
                </div>
              ))}
            </div>
          )}
          {activeRun.summary && (
            <p className="text-xs leading-relaxed text-slate-100">{activeRun.summary}</p>
          )}
        </div>
      )}

      {/* Recent Runs History */}
      {runs.length > 0 && (
        <div className="space-y-1.5">
          <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
            Histórico de missões
          </div>
          <div className="max-h-44 space-y-1.5 overflow-y-auto">
            {runs.map((run) => (
              <button
                key={run.id}
                type="button"
                onClick={() => setActiveRun(run)}
                className="flex w-full items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left text-xs transition hover:bg-white/10"
              >
                <div className="min-w-0">
                  <span className="mr-2 font-mono text-[10px] text-cyan-300">
                    {run.agent_name}
                  </span>
                  <span className="truncate text-slate-200">{run.goal}</span>
                </div>
                <span className="shrink-0 font-mono text-[10px] text-slate-400">{run.status}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
