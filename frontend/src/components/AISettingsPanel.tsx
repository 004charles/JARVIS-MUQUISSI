import { BellRing, CheckCircle2, Cloud, Cpu, Monitor, RefreshCw, Volume2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "../services/api";
import type {
  AIProviderInfo,
  AIProvidersResponse,
  DesktopStatusResponse,
  VoiceStatusResponse,
} from "../types/api";

interface AISettingsPanelProps {
  onConfigUpdated: (info: AIProvidersResponse) => void;
  onVoiceUpdated?: (voice: VoiceStatusResponse) => void;
  onTestVoice?: () => void;
}

export function AISettingsPanel({
  onConfigUpdated,
  onVoiceUpdated,
  onTestVoice,
}: AISettingsPanelProps) {
  const [data, setData] = useState<AIProvidersResponse | null>(null);
  const [voiceData, setVoiceData] = useState<VoiceStatusResponse | null>(null);
  const [desktopData, setDesktopData] = useState<DesktopStatusResponse | null>(null);
  const [selectedVoice, setSelectedVoice] = useState("Muquissi-Mulher");
  const [defaultProvider, setDefaultProvider] = useState("ollama");
  const [fallbackProvider, setFallbackProvider] = useState("");
  const [modelInput, setModelInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProviders = async () => {
    try {
      const [res, voiceRes, desktopRes] = await Promise.all([
        apiClient.getAIProviders(),
        apiClient.getVoiceStatus(),
        apiClient.getDesktopStatus().catch(() => null),
      ]);
      setData(res);
      setVoiceData(voiceRes);
      if (desktopRes) setDesktopData(desktopRes);
      setSelectedVoice(voiceRes.voice);
      setDefaultProvider(res.default_provider);
      setFallbackProvider(res.fallback_provider);
      const selected = res.providers.find((p) => p.name === res.default_provider);
      setModelInput(selected?.default_model ?? "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar providers.");
    }
  };

  useEffect(() => {
    void loadProviders();
  }, []);

  const selectedProvider: AIProviderInfo | undefined = data?.providers.find(
    (p) => p.name === defaultProvider,
  );

  const handleProviderChange = (nextName: string) => {
    setDefaultProvider(nextName);
    const found = data?.providers.find((p) => p.name === nextName);
    if (found) {
      setModelInput(found.default_model);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setStatusMessage(null);
    setError(null);
    try {
      const updated = await apiClient.updateAIConfig({
        default_provider: defaultProvider,
        fallback_provider: fallbackProvider,
        model: modelInput.trim() || undefined,
      });
      if (voiceData?.available && selectedVoice) {
        await apiClient.updateVoiceConfig(selectedVoice);
        const refreshedVoice = await apiClient.getVoiceStatus();
        setVoiceData(refreshedVoice);
        onVoiceUpdated?.(refreshedVoice);
      }
      setData(updated);
      onConfigUpdated(updated);
      setStatusMessage("Configuração de IA e voz guardada com sucesso.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao guardar configuração.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="my-auto w-full max-w-2xl space-y-4 rounded-2xl border border-cyan-500/25 bg-slate-950/70 p-5 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-cyan-500/15 pb-3">
        <div>
          <h2 className="font-mono text-xs uppercase tracking-[0.22em] text-cyan-300">
            Motor de Inteligência Artificial
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Seleciona o provider principal, modelo e alternativa de contingência.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadProviders()}
          className="flex items-center gap-1.5 rounded-lg border border-cyan-500/25 bg-slate-900/70 px-2.5 py-1.5 font-mono text-[11px] text-cyan-200 hover:border-cyan-400/60"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Atualizar
        </button>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {data.providers.map((provider) => (
              <button
                key={provider.name}
                type="button"
                onClick={() => handleProviderChange(provider.name)}
                className={`rounded-xl border p-3 text-left transition ${
                  defaultProvider === provider.name
                    ? "border-cyan-400/60 bg-cyan-500/15"
                    : "border-cyan-500/15 bg-slate-900/55 hover:border-cyan-500/35"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-100">
                    {provider.kind === "local" ? (
                      <Cpu className="h-4 w-4 text-cyan-300" />
                    ) : (
                      <Cloud className="h-4 w-4 text-sky-300" />
                    )}
                    {provider.name}
                  </span>
                  {provider.available ? (
                    <span className="flex items-center gap-1 font-mono text-[10px] text-emerald-300">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      ONLINE
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 font-mono text-[10px] text-slate-400">
                      <XCircle className="h-3.5 w-3.5 text-amber-400" />
                      INDISPONÍVEL
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-[11px] text-slate-400">{provider.detail}</p>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span className="block font-mono text-[10px] uppercase tracking-wider text-slate-400">
                Modelo ({defaultProvider})
              </span>
              <input
                type="text"
                value={modelInput}
                onChange={(e) => setModelInput(e.target.value)}
                placeholder="ex: qwen2.5-coder:7b"
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-xs text-slate-100 focus:border-cyan-400 focus:outline-none"
              />
              {selectedProvider && selectedProvider.models.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {selectedProvider.models.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setModelInput(m)}
                      className="rounded-md border border-cyan-500/20 bg-slate-900 px-2 py-0.5 font-mono text-[10px] text-cyan-200 hover:border-cyan-400"
                    >
                      {m}
                    </button>
                  ))}
                </div>
              )}
            </label>

            <label className="space-y-1 text-xs">
              <span className="block font-mono text-[10px] uppercase tracking-wider text-slate-400">
                Provider Alternativo (Fallback)
              </span>
              <select
                value={fallbackProvider}
                onChange={(e) => setFallbackProvider(e.target.value)}
                className="w-full rounded-xl border border-cyan-500/25 bg-slate-900/80 px-3 py-2 text-xs text-slate-100 focus:border-cyan-400 focus:outline-none"
              >
                <option value="">Nenhum</option>
                {data.providers
                  .filter((p) => p.name !== defaultProvider)
                  .map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-slate-400">
              Chaves externas são lidas apenas do ficheiro <code className="text-cyan-300">.env</code>.
            </span>
            <button
              type="button"
              disabled={saving}
              onClick={() => void handleSave()}
              className="rounded-xl border border-cyan-400/50 bg-cyan-500/20 px-4 py-2 font-mono text-xs text-cyan-100 transition hover:bg-cyan-500/30 disabled:opacity-50"
            >
              {saving ? "A guardar..." : "Guardar Configuração"}
            </button>
          </div>

          {voiceData && (
            <div className="mt-2 border-t border-cyan-500/15 pt-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Volume2 className="h-4 w-4 text-cyan-300" />
                  <span className="font-mono text-[11px] uppercase tracking-wider text-cyan-200">
                    Voz Natural ({voiceData.engine})
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${
                      voiceData.available
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {voiceData.available ? "ATIVA" : "FALLBACK BROWSER"}
                  </span>
                </div>

                {onTestVoice && (
                  <button
                    type="button"
                    onClick={onTestVoice}
                    className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 font-mono text-[10px] text-cyan-200 hover:bg-cyan-500/20"
                  >
                    Testar Voz
                  </button>
                )}
              </div>

              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {voiceData.available_voices.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setSelectedVoice(v)}
                    className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                      selectedVoice === v
                        ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                        : "border-cyan-500/20 bg-slate-900/60 text-slate-300 hover:border-cyan-500/40"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>

              {voiceData.native_supported && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/20 bg-slate-900/55 px-3 py-2 text-[11px]">
                  <div>
                    <span className="font-mono text-cyan-200">
                      Escuta Neural Ubuntu ({voiceData.neural_vad_available ? "Silero VAD ONNX" : "VAD"})
                    </span>
                    <p className="text-[10px] text-slate-400">
                      {voiceData.native_listening
                        ? "Ativa sem cliques no microfone do Ubuntu."
                        : "Em pausa."}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={async () => {
                        const nextReq = !(voiceData.require_wake_word ?? true);
                        await apiClient.updateNativeVoiceConfig(nextReq);
                        const refreshed = await apiClient.getVoiceStatus();
                        setVoiceData(refreshed);
                        onVoiceUpdated?.(refreshed);
                      }}
                      className="rounded-lg border border-cyan-500/30 bg-slate-950/70 px-2.5 py-1 font-mono text-[10px] text-cyan-200 hover:border-cyan-400"
                    >
                      {voiceData.require_wake_word ? 'Wake Word: "Arcanjo"' : "Modo Sempre Aberto"}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        if (voiceData.native_listening) {
                          await apiClient.stopNativeVoice();
                        } else {
                          await apiClient.startNativeVoice();
                        }
                        const refreshed = await apiClient.getVoiceStatus();
                        setVoiceData(refreshed);
                        onVoiceUpdated?.(refreshed);
                      }}
                      className={`rounded-lg border px-2.5 py-1 font-mono text-[10px] ${
                        voiceData.native_listening
                          ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
                          : "border-amber-400/50 bg-amber-500/15 text-amber-200"
                      }`}
                    >
                      {voiceData.native_listening ? "Desligar" : "Ligar"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {desktopData && (
            <div className="rounded-xl border border-cyan-500/20 bg-slate-950/65 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs text-slate-200">
                  <Monitor className="h-4 w-4 text-cyan-300" />
                  <span className="font-mono">Aplicação Desktop Ubuntu (Fase 10)</span>
                </div>
                <span className="font-mono text-[10px] text-slate-400">
                  {desktopData.notify_send_available ? "notify-send OK" : "sem notify-send"}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={async () => {
                    const updated = await apiClient.setDesktopAutostart(!desktopData.autostart_enabled);
                    setDesktopData(updated);
                    setStatusMessage(
                      updated.autostart_enabled
                        ? "Autostart Ubuntu ativado."
                        : "Autostart Ubuntu desativado.",
                    );
                  }}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                    desktopData.autostart_enabled
                      ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
                      : "border-cyan-500/25 bg-slate-900/70 text-slate-300"
                  }`}
                >
                  Autostart Ubuntu: {desktopData.autostart_enabled ? "Ativo" : "Desligado"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const updated = await apiClient.setDesktopNotifications(
                      !desktopData.desktop_notifications_enabled,
                    );
                    setDesktopData(updated);
                  }}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                    desktopData.desktop_notifications_enabled
                      ? "border-sky-400/50 bg-sky-500/15 text-sky-200"
                      : "border-cyan-500/25 bg-slate-900/70 text-slate-300"
                  }`}
                >
                  Notificações Nativas: {desktopData.desktop_notifications_enabled ? "Ativas" : "Desligadas"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const updated = await apiClient.installDesktopLauncher();
                    setDesktopData(updated);
                    setStatusMessage("Atalho do Arcanjo instalado no menu do Ubuntu.");
                  }}
                  className="rounded-lg border border-cyan-500/30 bg-slate-900/70 px-2.5 py-1 font-mono text-[11px] text-cyan-200 hover:border-cyan-400"
                >
                  {desktopData.desktop_entry_installed ? "Atualizar Atalho Ubuntu" : "Instalar Atalho Ubuntu"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const res = await apiClient.sendTestDesktopNotification();
                    setStatusMessage(
                      res.sent
                        ? "Notificação nativa enviada para o Ubuntu."
                        : "notify-send indisponível ou desativado.",
                    );
                  }}
                  className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/30 bg-slate-900/70 px-2.5 py-1 font-mono text-[11px] text-cyan-200 hover:border-cyan-400"
                >
                  <BellRing className="h-3 w-3" />
                  Testar Notificação
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {statusMessage && (
        <p className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {statusMessage}
        </p>
      )}
      {error && (
        <p className="rounded-xl border border-rose-500/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      )}
    </div>
  );
}
