import { Camera, CameraOff, Eye, RefreshCw, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { apiClient } from "../services/api";
import type { VisionStatusResponse } from "../types/api";

interface VisionPanelProps {
  cameraEnabled: boolean;
  cameraReady: boolean;
  cameraError: string | null;
  stream: MediaStream | null;
  onToggleCamera: () => Promise<void>;
  captureFrameB64: () => string | null;
  onSpeakDescription?: (description: string) => void;
}

export function VisionPanel({
  cameraEnabled,
  cameraReady,
  cameraError,
  stream,
  onToggleCamera,
  captureFrameB64,
  onSpeakDescription,
}: VisionPanelProps) {
  const [status, setStatus] = useState<VisionStatusResponse | null>(null);
  const [prompt, setPrompt] = useState("Descreve em português o que estás a ver neste momento.");
  const [analyzing, setAnalyzing] = useState(false);
  const [description, setDescription] = useState<string | null>(null);
  const [usedModel, setUsedModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const previewRef = useRef<HTMLVideoElement | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await apiClient.getVisionStatus();
      setStatus(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao verificar módulo de visão.");
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus, cameraReady]);

  useEffect(() => {
    const video = previewRef.current;
    if (!video) return;
    video.srcObject = stream;
    if (stream) {
      video.play().catch(() => undefined);
    }
  }, [stream]);

  const handleLookNow = async (event?: FormEvent) => {
    event?.preventDefault();
    if (analyzing) return;

    setAnalyzing(true);
    setError(null);

    try {
      const frame = captureFrameB64();
      const res = await apiClient.analyzeVision(
        prompt.trim() || "Descreve o que estás a ver na imagem.",
        frame ?? undefined,
      );
      setDescription(res.description);
      setUsedModel(res.model);
      onSpeakDescription?.(res.description);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao analisar imagem da câmara.");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">Visão &amp; Olhos do Muquissi</h3>
          <p className="text-xs text-slate-400">
            Liga a câmara do teu dispositivo (ou webcam Ubuntu) para o Muquissi ver em tempo real.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadStatus()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-slate-200 transition hover:bg-white/10"
            title="Atualizar estado"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Estado
          </button>
          <button
            type="button"
            onClick={() => void onToggleCamera()}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              cameraEnabled
                ? "bg-rose-500/20 text-rose-200 ring-1 ring-rose-400/40 hover:bg-rose-500/30"
                : "bg-sky-500 text-slate-950 hover:bg-sky-400"
            }`}
          >
            {cameraEnabled ? (
              <>
                <CameraOff className="h-3.5 w-3.5" />
                Desligar Câmara
              </>
            ) : (
              <>
                <Camera className="h-3.5 w-3.5" />
                Ligar Câmara
              </>
            )}
          </button>
        </div>
      </div>

      {/* Diagnostic Status Pills */}
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="text-[11px] text-slate-400">Câmara do Dispositivo</div>
          <div className="mt-1 flex items-center gap-1.5 text-xs font-medium">
            <span
              className={`h-2 w-2 rounded-full ${
                cameraReady
                  ? "bg-emerald-400"
                  : cameraEnabled
                    ? "bg-amber-400"
                    : "bg-slate-500"
              }`}
            />
            <span className="text-slate-100">
              {cameraReady
                ? "Pronta e conectada"
                : cameraEnabled
                  ? "A iniciar..."
                  : "Desligada"}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="text-[11px] text-slate-400">Ubuntu (/dev/video*)</div>
          <div className="mt-1 text-xs font-medium text-slate-100">
            {status
              ? status.local_cameras.length > 0
                ? `${status.local_cameras.join(", ")} (${status.ffmpeg_available ? "ffmpeg OK" : "sem ffmpeg"})`
                : "Sem webcam USB local"
              : "A verificar..."}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="text-[11px] text-slate-400">IA Multimodal</div>
          <div className="mt-1 text-xs font-medium text-slate-100">
            {status
              ? status.vision_ai_available
                ? `${status.model} (Ativo)`
                : "GEMINI_API_KEY em falta"
              : "A verificar..."}
          </div>
        </div>
      </div>

      {/* Live Preview */}
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/70">
        {stream ? (
          <video
            ref={previewRef}
            autoPlay
            playsInline
            muted
            className="aspect-video w-full object-cover"
          />
        ) : (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 text-slate-400">
            <Eye className="h-8 w-8 opacity-40" />
            <p className="text-xs">
              {status && status.local_cameras.length > 0
                ? "Câmara do navegador desligada — o Muquissi ainda pode usar a webcam Ubuntu."
                : "Clica em \"Ligar Câmara\" para dar olhos ao Muquissi."}
            </p>
          </div>
        )}
      </div>

      {(cameraError || error) && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {cameraError ?? error}
        </div>
      )}

      {/* Look Now Prompt */}
      <form onSubmit={(e) => void handleLookNow(e)} className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="O que queres que o Muquissi procure ou analise?"
          className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white placeholder:text-slate-400 focus:border-sky-400/60 focus:outline-none"
        />
        <button
          type="submit"
          disabled={analyzing}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {analyzing ? "A olhar..." : "Olhar Agora"}
        </button>
      </form>

      {description && (
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3">
          <div className="mb-1 flex items-center justify-between text-[11px] text-emerald-300">
            <span>O que o Muquissi viu</span>
            {usedModel && <span className="font-mono opacity-80">{usedModel}</span>}
          </div>
          <p className="text-xs leading-relaxed text-slate-100">{description}</p>
        </div>
      )}
    </div>
  );
}
