import { Calendar, CheckCircle2, Globe, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient } from "../services/api";
import type { AgendaEventItem, TaskEntryItem, WebSearchResultItem } from "../types/api";

interface ProductivityPanelProps {
  initialTab?: "tasks" | "agenda" | "web";
}

export function ProductivityPanel({ initialTab = "tasks" }: ProductivityPanelProps) {
  const [tab, setTab] = useState<"tasks" | "agenda" | "web">(initialTab);
  const [tasks, setTasks] = useState<TaskEntryItem[]>([]);
  const [agenda, setAgenda] = useState<AgendaEventItem[]>([]);
  const [taskTitle, setTaskTitle] = useState("");
  const [eventTitle, setEventTitle] = useState("");
  const [eventStart, setEventStart] = useState("");
  const [webQuery, setWebQuery] = useState("");
  const [webResults, setWebResults] = useState<WebSearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  const loadAll = async () => {
    const [t, a] = await Promise.all([apiClient.getTasks(), apiClient.getAgenda()]);
    setTasks(t);
    setAgenda(a);
  };

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  const handleAddTask = async (e: FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    await apiClient.createTask(taskTitle.trim());
    setTaskTitle("");
    await loadAll();
  };

  const handleAddEvent = async (e: FormEvent) => {
    e.preventDefault();
    if (!eventTitle.trim()) return;
    await apiClient.createAgendaEvent(eventTitle.trim(), eventStart || undefined);
    setEventTitle("");
    setEventStart("");
    await loadAll();
  };

  const handleWebSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!webQuery.trim()) return;
    setSearching(true);
    try {
      const res = await apiClient.searchWeb(webQuery.trim());
      setWebResults(res.results);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="w-full space-y-4 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/15 pb-3">
        <span className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
          Produtividade & Pesquisa Web
        </span>
        <div className="flex gap-1.5">
          {(
            [
              ["tasks", "Tarefas"],
              ["agenda", "Agenda"],
              ["web", "Internet"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] ${
                tab === id
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                  : "border-cyan-500/20 bg-slate-900/60 text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "tasks" && (
        <div className="space-y-3">
          <form onSubmit={(e) => void handleAddTask(e)} className="flex gap-2">
            <input
              type="text"
              value={taskTitle}
              onChange={(e) => setTaskTitle(e.target.value)}
              placeholder="Nova tarefa..."
              className="flex-1 rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 focus:outline-none"
            />
            <button
              type="submit"
              className="flex items-center gap-1 rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-3 py-2 font-mono text-cyan-100"
            >
              <Plus className="h-3.5 w-3.5" />
              Criar
            </button>
          </form>

          <div className="max-h-60 space-y-1.5 overflow-y-auto pr-1">
            {tasks.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-xl border border-cyan-500/15 bg-slate-900/60 px-3 py-2"
              >
                <button
                  type="button"
                  onClick={() =>
                    void apiClient
                      .updateTaskStatus(t.id, t.status === "done" ? "pending" : "done")
                      .then(loadAll)
                  }
                  className="flex items-center gap-2 text-left"
                >
                  <CheckCircle2
                    className={`h-4 w-4 ${
                      t.status === "done" ? "text-emerald-400" : "text-slate-500"
                    }`}
                  />
                  <span className={t.status === "done" ? "line-through text-slate-400" : "text-slate-100"}>
                    {t.title}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void apiClient.deleteTask(t.id).then(loadAll)}
                  className="text-slate-400 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "agenda" && (
        <div className="space-y-3">
          <form onSubmit={(e) => void handleAddEvent(e)} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_auto]">
            <input
              type="text"
              value={eventTitle}
              onChange={(e) => setEventTitle(e.target.value)}
              placeholder="Compromisso ou lembrete..."
              className="rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 focus:outline-none"
            />
            <input
              type="datetime-local"
              value={eventStart}
              onChange={(e) => setEventStart(e.target.value)}
              className="rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 focus:outline-none"
            />
            <button
              type="submit"
              className="flex items-center justify-center gap-1 rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-3 py-2 font-mono text-cyan-100"
            >
              <Calendar className="h-3.5 w-3.5" />
              Agendar
            </button>
          </form>

          <div className="max-h-60 space-y-1.5 overflow-y-auto pr-1">
            {agenda.map((ev) => (
              <div
                key={ev.id}
                className="flex items-center justify-between rounded-xl border border-cyan-500/15 bg-slate-900/60 px-3 py-2"
              >
                <div>
                  <p className="font-medium text-slate-100">{ev.title}</p>
                  <p className="font-mono text-[10px] text-cyan-300">
                    {new Date(ev.start_at).toLocaleString("pt-PT")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void apiClient.deleteAgendaEvent(ev.id).then(loadAll)}
                  className="text-slate-400 hover:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "web" && (
        <div className="space-y-3">
          <form onSubmit={(e) => void handleWebSearch(e)} className="flex gap-2">
            <input
              type="text"
              value={webQuery}
              onChange={(e) => setWebQuery(e.target.value)}
              placeholder="Pesquisar documentação ou informação na Web..."
              className="flex-1 rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-slate-100 focus:outline-none"
            />
            <button
              type="submit"
              disabled={searching}
              className="flex items-center gap-1 rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-3 py-2 font-mono text-cyan-100"
            >
              <Search className="h-3.5 w-3.5" />
              {searching ? "..." : "Pesquisar"}
            </button>
          </form>

          <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
            {webResults.map((r) => (
              <a
                key={r.url}
                href={r.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-xl border border-cyan-500/15 bg-slate-900/60 p-3 hover:border-cyan-400/50"
              >
                <p className="flex items-center gap-1.5 font-medium text-cyan-200">
                  <Globe className="h-3.5 w-3.5 shrink-0" />
                  {r.title}
                </p>
                {r.snippet && <p className="mt-1 text-[11px] text-slate-400">{r.snippet}</p>}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
