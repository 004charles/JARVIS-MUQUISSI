import { Brain, Check, Edit3, Plus, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiClient } from "../services/api";
import type { MemoryItem, OperationalMemoryItem } from "../types/api";

const CATEGORIES = [
  { id: "all", label: "Todas" },
  { id: "long_term", label: "Longo Prazo" },
  { id: "project", label: "Projetos" },
  { id: "preference", label: "Preferências" },
  { id: "operational", label: "Operacional" },
] as const;

export function MemoryPanel() {
  const [category, setCategory] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [operational, setOperational] = useState<OperationalMemoryItem[]>([]);
  const [newCategory, setNewCategory] = useState("long_term");
  const [newContent, setNewContent] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadMemories = useCallback(async () => {
    try {
      const res = await apiClient.getMemories(category, query);
      setItems(res.items);
      setOperational(res.operational);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar memórias.");
    }
  }, [category, query]);

  useEffect(() => {
    void loadMemories();
  }, [loadMemories]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = newContent.trim();
    if (!trimmed) return;
    try {
      await apiClient.createMemory(newCategory, trimmed);
      setNewContent("");
      setError(null);
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao guardar memória.");
    }
  };

  const handleSaveEdit = async (id: number) => {
    try {
      await apiClient.updateMemory(id, { content: editingText });
      setEditingId(null);
      setEditingText("");
      setError(null);
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao atualizar memória.");
    }
  };

  const handleDelete = async (id: number) => {
    await apiClient.deleteMemory(id);
    await loadMemories();
  };

  return (
    <div className="my-auto w-full max-w-3xl space-y-4 rounded-2xl border border-cyan-500/25 bg-slate-950/70 p-5 backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/15 pb-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-cyan-300" />
          <h2 className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
            Sistema de Memória Controlada
          </h2>
        </div>

        <div className="relative w-full sm:w-56">
          <Search className="pointer-events-none absolute top-2 left-2.5 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Pesquisar memórias..."
            className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 py-1.5 pr-3 pl-8 text-xs text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
          />
        </div>
      </div>

      {/* Category Pills */}
      <div className="flex flex-wrap gap-1.5">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            type="button"
            onClick={() => setCategory(cat.id)}
            className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] transition ${
              category === cat.id
                ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                : "border-cyan-500/20 bg-slate-900/60 text-slate-300 hover:border-cyan-400/50"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Add Memory Form */}
      {category !== "operational" && (
        <form onSubmit={(e) => void handleCreate(e)} className="flex flex-col gap-2 sm:flex-row">
          <select
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="rounded-xl border border-cyan-500/25 bg-slate-900/80 px-2.5 py-2 text-xs text-slate-100 focus:outline-none"
          >
            <option value="long_term">Longo Prazo</option>
            <option value="project">Projeto</option>
            <option value="preference">Preferência</option>
          </select>
          <input
            type="text"
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="Guardar informação ou contexto autorizado (nunca passwords/chaves)..."
            className="flex-1 rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!newContent.trim()}
            className="flex items-center justify-center gap-1 rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-3 py-2 font-mono text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
            Guardar
          </button>
        </form>
      )}

      {error && (
        <p className="rounded-xl border border-rose-500/40 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      )}

      {/* Operational Memory OR Persistent Memories */}
      {category === "operational" ? (
        <div className="max-h-60 space-y-1.5 overflow-y-auto pr-1 text-[11px] font-mono">
          {operational.length === 0 ? (
            <p className="text-slate-400">Sem ações operacionais registadas ainda.</p>
          ) : (
            operational.map((op) => (
              <div
                key={op.id}
                className="flex items-center justify-between rounded-xl border border-cyan-500/15 bg-slate-900/55 px-3 py-2"
              >
                <span className="truncate pr-3 text-slate-200">
                  <span className="text-cyan-300">{op.action_type}</span> · {op.target}
                </span>
                <span className="shrink-0 text-[10px] text-slate-400">{op.status}</span>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="max-h-60 space-y-2 overflow-y-auto pr-1 text-xs">
          {items.length === 0 ? (
            <p className="text-slate-400">
              Nenhuma memória encontrada. O Arcanjo pede confirmação antes de guardar factos novos.
            </p>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-cyan-500/15 bg-slate-900/60 p-3"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-cyan-300">
                      {item.category}
                    </span>
                    <span className="text-slate-400">fonte: {item.source}</span>
                    <span className="text-slate-500">
                      {new Date(item.created_at).toLocaleDateString("pt-PT")}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(item.id);
                        setEditingText(item.content);
                      }}
                      title="Editar memória"
                      className="text-slate-400 hover:text-cyan-300"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(item.id)}
                      title="Apagar memória"
                      className="text-slate-400 hover:text-rose-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {editingId === item.id ? (
                  <div className="mt-1.5 flex items-center gap-2">
                    <input
                      type="text"
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      className="flex-1 rounded-lg border border-cyan-400/40 bg-slate-950 px-2.5 py-1 text-xs text-slate-100 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => void handleSaveEdit(item.id)}
                      className="rounded-lg bg-emerald-500/20 p-1 text-emerald-300 hover:bg-emerald-500/30"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="rounded-lg bg-slate-800 p-1 text-slate-300"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : (
                  <p className="text-slate-200">{item.content}</p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
