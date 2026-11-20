import { MessageSquarePlus, MessagesSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "../services/api";
import type { ChatMessageItem, ConversationSummary } from "../types/api";

interface ConversationsPanelProps {
  activeConversationId: number | null;
  messages: ChatMessageItem[];
  onSelectConversation: (conversationId: number, loadedMessages: ChatMessageItem[]) => void;
  onNewConversation: () => void;
}

export function ConversationsPanel({
  activeConversationId,
  messages,
  onSelectConversation,
  onNewConversation,
}: ConversationsPanelProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const loadList = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getConversations();
      setConversations(list);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadList();
  }, [activeConversationId]);

  const handleOpen = async (convId: number) => {
    const persisted = await apiClient.getMessages(convId);
    const mapped: ChatMessageItem[] = persisted.map((m) => ({
      id: `db-${m.id}`,
      role: m.role,
      content: m.content,
      timestamp: m.created_at,
    }));
    onSelectConversation(convId, mapped);
  };

  return (
    <div className="my-auto grid w-full max-w-3xl grid-cols-1 gap-4 rounded-2xl border border-cyan-500/25 bg-slate-950/70 p-5 backdrop-blur-md md:grid-cols-[240px_1fr]">
      <div className="flex flex-col border-b border-cyan-500/15 pb-3 md:border-r md:border-b-0 md:pr-4 md:pb-0">
        <div className="mb-3 flex items-center justify-between">
          <span className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-widest text-cyan-300">
            <MessagesSquare className="h-3.5 w-3.5" />
            Histórico
          </span>
          <button
            type="button"
            onClick={onNewConversation}
            title="Nova conversa"
            className="flex items-center gap-1 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2 py-1 font-mono text-[10px] text-cyan-200 hover:bg-cyan-500/20"
          >
            <MessageSquarePlus className="h-3 w-3" />
            Nova
          </button>
        </div>

        <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
          {loading && conversations.length === 0 ? (
            <p className="text-xs text-slate-400">A carregar...</p>
          ) : conversations.length === 0 ? (
            <p className="text-xs text-slate-400">Ainda sem conversas guardadas.</p>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                type="button"
                onClick={() => void handleOpen(conv.id)}
                className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${
                  activeConversationId === conv.id
                    ? "border-cyan-400/50 bg-cyan-500/15 text-cyan-100"
                    : "border-cyan-500/10 bg-slate-900/50 text-slate-300 hover:border-cyan-500/30"
                }`}
              >
                <p className="truncate font-medium">{conv.title}</p>
                <p className="mt-0.5 font-mono text-[10px] text-slate-400">
                  #{conv.id}
                </p>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="flex flex-col">
        <h2 className="mb-2 font-mono text-[11px] uppercase tracking-widest text-cyan-300">
          {activeConversationId ? `Conversa #${activeConversationId}` : "Nova Sessão"}
        </h2>
        <div className="max-h-64 flex-1 space-y-2 overflow-y-auto pr-1 text-xs">
          {messages.length === 0 ? (
            <p className="text-slate-400">
              Envia uma mensagem na barra inferior para iniciar a conversa com o Muquissi.
            </p>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`rounded-xl border px-3 py-2 ${
                  m.role === "user"
                    ? "border-sky-500/30 bg-sky-500/10 text-sky-100"
                    : "border-cyan-500/25 bg-slate-900/75 text-cyan-100"
                }`}
              >
                <span className="mr-2 font-mono text-[10px] uppercase text-cyan-400">
                  {m.role === "user" ? "Carlos" : "Muquissi"}:
                </span>
                {m.content}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
