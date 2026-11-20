import { FolderGit2, Plus, SearchCheck, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient } from "../services/api";
import type { ProjectAnalysisReport, ProjectEntryItem } from "../types/api";

export function ProjectsPanel() {
  const [projects, setProjects] = useState<ProjectEntryItem[]>([]);
  const [name, setName] = useState("");
  const [directory, setDirectory] = useState("");
  const [report, setReport] = useState<ProjectAnalysisReport | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = async () => {
    try {
      setProjects(await apiClient.getProjects());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar projetos.");
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !directory.trim()) return;
    try {
      await apiClient.createProject({ name: name.trim(), directory: directory.trim() });
      setName("");
      setDirectory("");
      setError(null);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao registar projeto.");
    }
  };

  const handleAnalyze = async (id: number) => {
    setAnalyzingId(id);
    setError(null);
    try {
      const res = await apiClient.analyzeProject(id);
      setReport(res.report);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao analisar projeto.");
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="w-full space-y-4 text-xs">
      <div className="flex items-center gap-2 border-b border-cyan-500/15 pb-3">
        <FolderGit2 className="h-4 w-4 text-cyan-400" />
        <h2 className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
          Gestão & Análise de Projetos
        </h2>
      </div>

      <form onSubmit={(e) => void handleCreate(e)} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1.5fr_auto]">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nome (ex: Muquissi)"
          className="rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 placeholder:text-slate-500 focus:outline-none"
        />
        <input
          type="text"
          value={directory}
          onChange={(e) => setDirectory(e.target.value)}
          placeholder="Diretório autorizado (ex: .)"
          className="rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 placeholder:text-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          className="flex items-center justify-center gap-1 rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-3 py-2 font-mono text-cyan-100 hover:bg-cyan-500/30"
        >
          <Plus className="h-3.5 w-3.5" />
          Adicionar
        </button>
      </form>

      {error && (
        <p className="rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-rose-200">
          {error}
        </p>
      )}

      <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
        {projects.length === 0 ? (
          <p className="text-slate-400">Nenhum projeto registado ainda.</p>
        ) : (
          projects.map((p) => (
            <div
              key={p.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/15 bg-slate-900/60 p-3"
            >
              <div className="min-w-0">
                <p className="font-semibold text-cyan-100">{p.name}</p>
                <p className="truncate font-mono text-[10px] text-slate-400">{p.directory}</p>
                {p.technologies && (
                  <p className="mt-1 font-mono text-[10px] text-cyan-300">{p.technologies}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={analyzingId === p.id}
                  onClick={() => void handleAnalyze(p.id)}
                  className="flex items-center gap-1 rounded-lg border border-cyan-500/35 bg-cyan-500/15 px-2.5 py-1 font-mono text-[10px] text-cyan-200 hover:bg-cyan-500/25"
                >
                  <SearchCheck className="h-3.5 w-3.5" />
                  {analyzingId === p.id ? "A analisar..." : "Analisar"}
                </button>
                <button
                  type="button"
                  onClick={() => void apiClient.deleteProject(p.id).then(loadProjects)}
                  className="text-slate-400 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {report && (
        <div className="space-y-2 rounded-xl border border-cyan-500/25 bg-slate-900/75 p-3.5">
          <p className="font-mono text-[11px] uppercase tracking-wider text-cyan-300">
            Relatório: {report.directory} ({report.total_files_scanned} ficheiros)
          </p>
          <p className="text-slate-200">
            <strong>Stack:</strong> {report.technologies.join(", ") || "N/D"}
          </p>
          {report.git.initialized && (
            <p className="font-mono text-[11px] text-slate-300">
              Git: {report.git.status.split("\n")[0]}
            </p>
          )}
          {report.issues.length > 0 && (
            <ul className="list-disc pl-4 text-amber-200">
              {report.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          )}
          <ul className="list-disc pl-4 text-emerald-200">
            {report.recommendations.map((rec) => (
              <li key={rec}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
