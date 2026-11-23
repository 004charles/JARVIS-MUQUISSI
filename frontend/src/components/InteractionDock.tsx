import { Mic, MicOff, Send, Square, Volume2, VolumeX } from "lucide-react";
import type { FormEvent } from "react";
import type {
  AmbientHeardItem,
  AssistantState,
  ChatMessageItem,
  ListeningMode,
} from "../types/api";

interface InteractionDockProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (e: FormEvent) => void;
  onToggleListening: () => void;
  onInterrupt: () => void;
  voiceEnabled: boolean;
  ttsAvailable: boolean;
  onToggleVoice: () => void;
  micActive: boolean;
  nativeListening: boolean;
  nativeSignalDetected: boolean;
  nativeWindowActive: boolean;
  listeningMode: ListeningMode;
  onChangeListeningMode: (mode: ListeningMode) => void;
  recentHeard: AmbientHeardItem[];
  transcribing: boolean;
  micLevel: number;
  micError: string | null;
  assistantState: AssistantState;
  latestReply: ChatMessageItem | null;
  streamingText: string;
  aiError: string | null;
}

const MODE_LABELS: Array<{ id: ListeningMode; label: string; hint: string }> = [
  { id: "proactive", label: "Opinião Ativa", hint: "Ouve a sala e dá opiniões" },
  { id: "always_reply", label: "Responder a Tudo", hint: "Responde a cada frase" },
  { id: "wake_word", label: "Só por Nome", hint: "Requer dizer 'Arcanjo'" },
];

export function InteractionDock({
  input,
  onInputChange,
  onSubmit,
  onToggleListening,
  onInterrupt,
  voiceEnabled,
  ttsAvailable,
  onToggleVoice,
  micActive,
  nativeListening,
  nativeSignalDetected,
  nativeWindowActive,
  listeningMode,
  onChangeListeningMode,
  recentHeard,
  transcribing,
  micLevel,
  micError,
  assistantState,
  latestReply,
  streamingText,
  aiError,
}: InteractionDockProps) {
  const isBusy = assistantState === "processing" || assistantState === "speaking";
  const showTextReply = !voiceEnabled || !ttsAvailable;
  const displayedReply = showTextReply ? streamingText || latestReply?.content || "" : "";

  return (
    <div className="z-20 mx-auto w-full max-w-3xl space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/20 bg-slate-900/60 px-3 py-2">
        <span className="font-mono text-[11px] text-slate-300">Modo de Participação:</span>
        <div className="flex flex-wrap gap-1.5">
          {MODE_LABELS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onChangeListeningMode(item.id)}
              title={item.hint}
              className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
                listeningMode === item.id
                  ? "border-emerald-400 bg-emerald-500/20 font-medium text-emerald-200"
                  : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {(micActive || (nativeListening && nativeSignalDetected)) && (
        <div className="flex items-center justify-between rounded-xl border border-sky-400/35 bg-sky-950/55 px-4 py-1.5 text-[11px] font-mono text-sky-200 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 animate-pulse rounded-full bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.9)]" />
            <span>
              {transcribing
                ? "A TRANSCREVER VOZ..."
                : isBusy
                  ? "A PENSAR / A FALAR..."
                  : listeningMode === "proactive"
                    ? "ESCUTA DE SALA ATIVA — A OUVIR E A OPINAR NATURALMENTE"
                    : nativeWindowActive || listeningMode === "always_reply"
                      ? "CONVERSA ABERTA — PODE FALAR"
                      : "PASSIVO — DIGA 'ARCANJO' PARA CHAMAR"}
            </span>
          </div>
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-sky-400 transition-all duration-75"
              style={{
                width: `${
                  nativeListening && nativeSignalDetected && !micActive
                    ? assistantState === "listening"
                      ? 65
                      : 18
                    : Math.min(100, Math.round(micLevel * 100))
                }%`,
              }}
            />
          </div>
        </div>
      )}

      {!micActive && nativeListening && !nativeSignalDetected && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
          Microfone Ubuntu sem sinal físico detetado. Clica no botão do microfone abaixo para ativar o microfone do navegador.
        </div>
      )}

      {(aiError || micError) && (
        <div className="rounded-xl border border-rose-500/45 bg-rose-950/75 px-4 py-2.5 text-xs leading-relaxed text-rose-100 backdrop-blur-md">
          <span className="mr-2 font-mono text-[10px] tracking-widest text-rose-300">
            AVISO:
          </span>
          {aiError || micError}
        </div>
      )}

      {!aiError && displayedReply && (
        <div className="max-h-36 overflow-y-auto rounded-xl border border-cyan-500/25 bg-slate-950/75 px-4 py-2.5 text-xs leading-relaxed text-cyan-100 backdrop-blur-md shadow-[0_0_24px_rgba(6,182,212,0.12)]">
          <span className="mr-2 font-mono text-[10px] tracking-widest text-cyan-400">
            ARCANJO:
          </span>
          <span className="whitespace-pre-wrap">{displayedReply}</span>
          {streamingText && (
            <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-cyan-300 align-middle" />
          )}
        </div>
      )}

      <form
        onSubmit={onSubmit}
        className="flex items-center gap-2 rounded-2xl border border-cyan-500/30 bg-slate-950/75 p-2 backdrop-blur-xl shadow-[0_0_32px_rgba(34,211,238,0.14)]"
      >
        <button
          type="button"
          onClick={onToggleListening}
          title={
            micActive || (nativeListening && nativeSignalDetected)
              ? "Desativar escuta por voz"
              : "Ativar escuta contínua por voz"
          }
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition ${
            micActive || (nativeListening && nativeSignalDetected)
              ? "border-sky-400 bg-sky-500/25 text-sky-200 shadow-[0_0_16px_rgba(56,189,248,0.45)]"
              : "border-cyan-500/25 bg-slate-900/70 text-cyan-300 hover:border-cyan-400/60"
          }`}
        >
          {micActive || (nativeListening && nativeSignalDetected) ? (
            <Mic className="h-4 w-4" />
          ) : (
            <MicOff className="h-4 w-4" />
          )}
        </button>

        <input
          type="text"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="Olá, Carlos. Como posso ajudar hoje?"
          className="w-full bg-transparent px-2 text-sm text-slate-100 placeholder:text-slate-400 focus:outline-none"
        />

        <button
          type="button"
          onClick={onToggleVoice}
          title={voiceEnabled ? "Silenciar voz" : "Ativar voz do navegador"}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-500/20 bg-slate-900/70 text-slate-300 transition hover:border-cyan-400/50 hover:text-cyan-200"
        >
          {voiceEnabled ? <Volume2 className="h-4 w-4 text-cyan-300" /> : <VolumeX className="h-4 w-4" />}
        </button>

        {isBusy && (
          <button
            type="button"
            onClick={onInterrupt}
            title="Interromper resposta"
            className="flex h-10 shrink-0 items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-500/15 px-3 font-mono text-xs text-rose-200 transition hover:bg-rose-500/25"
          >
            <Square className="h-3.5 w-3.5" />
            Parar
          </button>
        )}

        <button
          type="submit"
          disabled={!input.trim()}
          title="Enviar mensagem"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-400/45 bg-cyan-500/20 text-cyan-200 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>

      {recentHeard.length > 0 && (
        <div className="space-y-1 rounded-xl border border-white/10 bg-slate-950/60 p-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
            Últimas falas ouvidas na sala
          </div>
          <div className="max-h-28 space-y-1 overflow-y-auto text-xs">
            {recentHeard.map((item, idx) => (
              <div key={`${item.time}-${idx}`} className="flex gap-2 text-slate-300">
                <span className="shrink-0 font-mono text-[10px] text-slate-500">{item.time}</span>
                <span
                  className={`shrink-0 font-medium ${
                    item.speaker === "Arcanjo" ? "text-emerald-300" : "text-sky-300"
                  }`}
                >
                  {item.speaker}:
                </span>
                <span className="text-slate-200">{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
