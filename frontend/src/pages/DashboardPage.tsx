import { Bell, Cloud, Eye, Menu, Mic, MicOff, MoonStar, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { AISettingsPanel } from "../components/AISettingsPanel";
import { AgentsPanel } from "../components/AgentsPanel";
import { ApprovalBanner } from "../components/ApprovalBanner";
import { BackdropCanvas, type BackdropTheme } from "../components/BackdropCanvas";
import { ConversationsPanel } from "../components/ConversationsPanel";
import { InteractionDock } from "../components/InteractionDock";
import { JarvisCoreWheel } from "../components/JarvisCoreWheel";
import { MemoryPanel } from "../components/MemoryPanel";
import { NotificationsPopover } from "../components/NotificationsPopover";
import { ProductivityPanel } from "../components/ProductivityPanel";
import { ProjectsPanel } from "../components/ProjectsPanel";
import { SystemMonitorPanel } from "../components/SystemMonitorPanel";
import { ToolsSecurityPanel } from "../components/ToolsSecurityPanel";
import { VisionPanel } from "../components/VisionPanel";
import { useCameraVision } from "../hooks/useCameraVision";
import { useContinuousVoice } from "../hooks/useContinuousVoice";
import { useJarvisSocket } from "../hooks/useJarvisSocket";
import { useSpeechQueue } from "../hooks/useSpeechQueue";
import { apiClient } from "../services/api";
import type {
  AIProvidersResponse,
  AssistantState,
  ChatMessageItem,
  FaceMood,
  ListeningMode,
  NotificationItem,
  SystemSnapshot,
  VoiceStatusResponse,
} from "../types/api";

type DrawerTab =
  | "chat"
  | "agents"
  | "vision"
  | "projects"
  | "system"
  | "memory"
  | "tasks"
  | "agenda"
  | "web"
  | "conversations"
  | "tools"
  | "settings";

const THEME_OPTIONS: Array<{ id: BackdropTheme; label: string }> = [
  { id: "clouds", label: "Nuvens" },
  { id: "galaxy", label: "Galáxia" },
  { id: "aurora", label: "Aurora" },
];

export function DashboardPage() {
  const [theme, setTheme] = useState<BackdropTheme>(() => {
    const saved = localStorage.getItem("muquissi_theme") as BackdropTheme | null;
    return saved && ["clouds", "galaxy", "aurora"].includes(saved) ? saved : "clouds";
  });
  const [autoCycleTheme, setAutoCycleTheme] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("chat");

  const [system, setSystem] = useState<SystemSnapshot | null>(null);
  const [, setAiProviders] = useState<AIProvidersResponse | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatusResponse | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [input, setInput] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const sendCommandRef = useRef<(msg: Record<string, unknown>) => void>(() => undefined);
  const respondToCaptureRequestRef = useRef<(requestId: string) => void>(() => undefined);

  const {
    speechEnergy,
    unlockAudio,
    pushStreamDelta,
    flushStreamEnd,
    speakImmediate,
    stopAll,
  } = useSpeechQueue({
    voiceEnabled,
    ttsAvailable: Boolean(voiceStatus?.available),
    voiceName: voiceStatus?.voice ?? "Muquissi-Grave",
    onSpeakingStart: useCallback(() => {
      sendCommandRef.current({ type: "assistant.set_state", state: "speaking" });
    }, []),
    onSpeakingEnd: useCallback(() => {
      sendCommandRef.current({
        type: "assistant.set_state",
        state: "idle",
      });
    }, []),
  });

  const {
    connected,
    assistantState,
    faceMood,
    systemUpdate,
    messages,
    latestReply,
    streamingText,
    activeConversationId,
    aiError,
    streamPulse,
    pendingApprovals,
    activeToolLabel,
    activeAgentLabel,
    latestAgentRun,
    nativeWindowActive,
    recentHeard,
    listeningMode,
    setActiveConversationId,
    setMessages,
    removePendingApproval,
    clearError,
    sendCommand,
    appendLocalMessage,
  } = useJarvisSocket({
    onStreamStart: stopAll,
    onStreamDelta: pushStreamDelta,
    onStreamEnd: (fullText, spokenNatively) => {
      if (!spokenNatively) {
        flushStreamEnd(fullText);
      }
    },
    onNotification: (item) => {
      setNotifications((prev) =>
        prev.some((n) => n.id === item.id) ? prev : [item, ...prev].slice(0, 30),
      );
      setUnreadCount((c) => c + 1);
    },
    onVisionCaptureRequest: (requestId) => {
      respondToCaptureRequestRef.current(requestId);
    },
  });
  sendCommandRef.current = sendCommand;

  const {
    cameraEnabled,
    cameraReady,
    cameraError,
    stream: cameraStream,
    videoRef: cameraVideoRef,
    toggleCamera,
    captureFrameB64,
    respondToCaptureRequest,
  } = useCameraVision({
    connected,
    sendCommand,
  });
  respondToCaptureRequestRef.current = respondToCaptureRequest;

  const handleVoiceTranscript = useCallback(
    (text: string) => {
      clearError();
      sendCommand({
        type: "voice.ambient_utterance",
        content: text,
        conversation_id: activeConversationId,
      });
    },
    [activeConversationId, clearError, sendCommand],
  );

  const handleVoiceStateHint = useCallback(
    (state: AssistantState) => {
      sendCommand({ type: "assistant.set_state", state });
    },
    [sendCommand],
  );

  const { micActive, transcribing, micLevel, micError, toggleMic, startMic } = useContinuousVoice({
    assistantState,
    autoStartAllowed: Boolean(voiceStatus),
    onTranscript: handleVoiceTranscript,
    onStateHint: handleVoiceStateHint,
  });

  // Tell backend whether browser microphone is actively handling room audio
  useEffect(() => {
    if (!connected) return;
    sendCommand({ type: "voice.browser_mic", active: micActive });
  }, [connected, micActive, sendCommand]);

  // Unlock browser audio + hands-free microphone automatically on first user gesture anywhere
  useEffect(() => {
    const onFirstGesture = () => {
      void unlockAudio();
      if (!micActive && localStorage.getItem("jarvis_browser_mic_disabled") !== "1") {
        startMic();
      }
    };
    window.addEventListener("pointerdown", onFirstGesture, { once: true });
    window.addEventListener("keydown", onFirstGesture, { once: true });
    return () => {
      window.removeEventListener("pointerdown", onFirstGesture);
      window.removeEventListener("keydown", onFirstGesture);
    };
  }, [micActive, startMic, unlockAudio]);

  useEffect(() => {
    localStorage.setItem("muquissi_theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!autoCycleTheme) return;
    const order: BackdropTheme[] = ["clouds", "galaxy", "aurora"];
    const timer = window.setInterval(() => {
      setTheme((curr) => order[(order.indexOf(curr) + 1) % order.length]);
    }, 45000);
    return () => window.clearInterval(timer);
  }, [autoCycleTheme]);

  useEffect(() => {
    let mounted = true;
    let retryTimer: number | undefined;
    let attempts = 0;

    const loadInitial = async () => {
      try {
        const [systemData, aiData, voiceData, notifData] = await Promise.all([
          apiClient.getSystemStatus(),
          apiClient.getAIProviders(),
          apiClient.getVoiceStatus(),
          apiClient.getNotifications(25),
        ]);
        if (!mounted) return;
        setSystem(systemData);
        setAiProviders(aiData);
        setVoiceStatus(voiceData);
        setNotifications(notifData.items);
        setUnreadCount(notifData.unread_count);
        setError(null);
      } catch (err) {
        if (!mounted) return;
        attempts += 1;
        if (attempts <= 6) {
          retryTimer = window.setTimeout(() => {
            if (mounted) void loadInitial();
          }, 1500);
          return;
        }
        setError(err instanceof Error ? err.message : "Falha ao contactar backend.");
      }
    };
    void loadInitial();
    return () => {
      mounted = false;
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [connected]);

  const stopSpeech = useCallback(() => {
    stopAll();
    sendCommand({ type: "assistant.interrupt" });
  }, [sendCommand, stopAll]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    void unlockAudio();
    clearError();
    appendLocalMessage("user", trimmed);
    sendCommand({
      type: "chat.send",
      content: trimmed,
      conversation_id: activeConversationId,
    });
    setInput("");
  };

  const handleToggleListening = async () => {
    await unlockAudio();
    toggleMic();
  };

  const handleChangeListeningMode = async (mode: ListeningMode) => {
    await apiClient.setListeningMode(mode);
    const refreshed = await apiClient.getVoiceStatus();
    setVoiceStatus(refreshed);
  };

  const handleCoreClick = async () => {
    clearError();
    await unlockAudio();
    if (!micActive) {
      startMic();
    }
    sendCommand({ type: "assistant.greet" });
  };

  const handleSelectConversation = (convId: number, loadedMessages: ChatMessageItem[]) => {
    setActiveConversationId(convId);
    setMessages(loadedMessages);
  };

  const handleNewConversation = () => {
    setActiveConversationId(null);
    setMessages([]);
    clearError();
  };

  const currentSystem = systemUpdate ?? system;
  const isLight = theme === "clouds";

  const isHardwareStressed = Boolean(
    currentSystem &&
      (currentSystem.cpu_percent >= 88 ||
        currentSystem.ram_percent >= 90 ||
        (currentSystem.temperature_celsius ?? 0) >= 80),
  );
  const hourNow = new Date().getHours();
  const isLateNight = hourNow >= 23 || hourNow < 5;

  const effectiveMood: FaceMood =
    assistantState === "error"
      ? "sad"
      : faceMood !== "neutral"
        ? faceMood
        : isHardwareStressed || isLateNight
          ? "tired"
          : assistantState === "listening"
            ? "curious"
            : assistantState === "processing" || assistantState === "executing"
              ? "thinking"
              : "neutral";

  return (
    <div
      className={`relative min-h-screen overflow-hidden ${
        isLight ? "text-slate-900" : "text-slate-100"
      }`}
    >
      {/* Dynamic Full-Screen Backdrop (Clouds / Galaxy / Aurora) */}
      <BackdropCanvas theme={theme} />

      {/* Background Device Camera Feed for Hands-Free Vision */}
      <video ref={cameraVideoRef} playsInline muted className="hidden" />

      {/* Whisper-Subtle Corner Control (zero sidebars or edge clutter) */}
      <div className="fixed top-4 right-4 z-30 flex items-center gap-2 opacity-25 transition-opacity duration-300 hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          onClick={() => void handleToggleListening()}
          title={
            micActive || (voiceStatus?.native_listening && voiceStatus?.native_signal_detected)
              ? "Escuta de sala ativa (clique para alternar)"
              : "Ligar microfone para o Muquissi ouvir e opinar"
          }
          className={`flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-md transition ${
            micActive || (voiceStatus?.native_listening && voiceStatus?.native_signal_detected)
              ? isLight
                ? "border-sky-400/75 bg-white/80 text-sky-700 hover:bg-white"
                : "border-sky-400/50 bg-slate-950/60 text-sky-300 hover:bg-slate-900"
              : isLight
                ? "border-sky-300/60 bg-white/70 text-slate-500 hover:bg-white"
                : "border-cyan-500/30 bg-slate-950/60 text-slate-400 hover:bg-slate-900"
          }`}
        >
          {micActive || (voiceStatus?.native_listening && voiceStatus?.native_signal_detected) ? (
            <Mic className="h-4 w-4" />
          ) : (
            <MicOff className="h-4 w-4" />
          )}
        </button>
        {cameraReady && (
          <button
            type="button"
            onClick={() => {
              setDrawerTab("vision");
              setDrawerOpen(true);
            }}
            title="Visão ativa (câmara conectada)"
            className={`flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-md transition ${
              isLight
                ? "border-emerald-400/70 bg-white/75 text-emerald-700 hover:bg-white"
                : "border-emerald-400/40 bg-slate-950/60 text-emerald-300 hover:bg-slate-900"
            }`}
          >
            <Eye className="h-4 w-4" />
          </button>
        )}
        {unreadCount > 0 && (
          <NotificationsPopover
            open={notifOpen}
            unreadCount={unreadCount}
            items={notifications}
            onToggle={() => setNotifOpen((o) => !o)}
            onMarkAllRead={() => {
              void apiClient.markAllNotificationsRead().then(() => {
                setUnreadCount(0);
                setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
              });
            }}
          />
        )}
        <button
          type="button"
          onClick={() => setDrawerOpen((o) => !o)}
          title="Abrir painéis do Muquissi"
          className={`flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-md transition ${
            isLight
              ? "border-sky-300/60 bg-white/70 text-sky-900 hover:bg-white"
              : "border-cyan-500/30 bg-slate-950/60 text-cyan-200 hover:bg-slate-900"
          }`}
        >
          {drawerOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      {/* Pure Center Stage: ONLY Backdrop + Muquissi in the Center */}
      <main className="relative z-10 flex min-h-screen flex-col items-center justify-center p-4">
        <JarvisCoreWheel
          state={assistantState}
          mood={effectiveMood}
          speechEnergy={Math.max(speechEnergy, streamPulse, micLevel)}
          theme={theme}
          onCoreClick={() => void handleCoreClick()}
        />

        {(activeToolLabel || activeAgentLabel || pendingApprovals.length > 0 || error || aiError || micError) && (
          <div className="fixed right-4 bottom-4 left-4 z-30 mx-auto max-w-2xl space-y-2">
            {(activeToolLabel || activeAgentLabel) && (
              <div className="mx-auto w-fit rounded-full border border-emerald-400/50 bg-emerald-950/80 px-4 py-1 font-mono text-[11px] text-emerald-200 backdrop-blur-md">
                {activeAgentLabel || activeToolLabel}
              </div>
            )}

            <ApprovalBanner
              approvals={pendingApprovals}
              onResolved={(id, feedback) => {
                removePendingApproval(id);
                appendLocalMessage("assistant", feedback);
              }}
            />

            {(error || aiError || micError) && (
              <div className="rounded-xl border border-rose-500/45 bg-rose-950/85 px-4 py-2 text-center text-xs text-rose-100 backdrop-blur-md">
                {error || aiError || micError}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Optional Glassmorphic Overlay Modal for Settings / Projects / System / Chat */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-sm"
          onClick={() => setDrawerOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[88vh] w-full max-w-4xl flex-col gap-4 overflow-y-auto rounded-3xl border border-cyan-500/30 bg-slate-950/90 p-5 text-slate-100 shadow-[0_0_50px_rgba(14,165,233,0.25)] backdrop-blur-xl"
          >
            {/* Overlay Header: Tabs + Background Switcher */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-3">
              <div className="flex flex-wrap gap-1.5">
                {(
                  [
                    ["chat", "Texto & Voz"],
                    ["agents", "Agentes"],
                    ["vision", "Visão"],
                    ["projects", "Projetos"],
                    ["tasks", "Tarefas"],
                    ["agenda", "Agenda"],
                    ["web", "Internet"],
                    ["system", "Sistema"],
                    ["memory", "Memória"],
                    ["conversations", "Conversas"],
                    ["tools", "Segurança"],
                    ["settings", "Configurações"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setDrawerTab(id)}
                    className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition ${
                      drawerTab === id
                        ? "border-cyan-400 bg-cyan-500/20 text-cyan-100"
                        : "border-cyan-500/20 bg-slate-900/60 text-slate-300 hover:border-cyan-400/50"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1.5 font-mono text-[10px]">
                {THEME_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      setAutoCycleTheme(false);
                      setTheme(opt.id);
                    }}
                    className={`flex items-center gap-1 rounded-full border px-2.5 py-1 transition ${
                      theme === opt.id && !autoCycleTheme
                        ? "border-cyan-300 bg-cyan-500/25 text-cyan-100"
                        : "border-cyan-500/20 bg-slate-900/60 text-slate-300"
                    }`}
                  >
                    {opt.id === "clouds" ? (
                      <Cloud className="h-3 w-3" />
                    ) : opt.id === "galaxy" ? (
                      <MoonStar className="h-3 w-3" />
                    ) : (
                      <Sparkles className="h-3 w-3" />
                    )}
                    {opt.label}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setAutoCycleTheme((v) => !v)}
                  className={`rounded-full border px-2.5 py-1 transition ${
                    autoCycleTheme
                      ? "border-emerald-400 bg-emerald-500/20 text-emerald-200"
                      : "border-cyan-500/20 bg-slate-900/60 text-slate-400"
                  }`}
                >
                  Auto
                </button>
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="ml-1 rounded-full border border-slate-700 p-1.5 text-slate-300 hover:text-white"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Active Panel Content */}
            {drawerTab === "chat" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>Estado da escuta e envio por texto</span>
                  <button
                    type="button"
                    onClick={() => setDrawerTab("system")}
                    className="flex items-center gap-1 text-cyan-300 hover:underline"
                  >
                    <Bell className="h-3.5 w-3.5" />
                    {unreadCount} notificações
                  </button>
                </div>
                <InteractionDock
                  input={input}
                  onInputChange={setInput}
                  onSubmit={handleSubmit}
                  onToggleListening={() => void handleToggleListening()}
                  onInterrupt={stopSpeech}
                  voiceEnabled={voiceEnabled}
                  ttsAvailable={Boolean(voiceStatus?.available)}
                  onToggleVoice={() => setVoiceEnabled((v) => !v)}
                  micActive={micActive}
                  nativeListening={Boolean(voiceStatus?.native_listening)}
                  nativeSignalDetected={Boolean(voiceStatus?.native_signal_detected)}
                  nativeWindowActive={
                    nativeWindowActive || Boolean(voiceStatus?.window_active)
                  }
                  listeningMode={voiceStatus?.listening_mode ?? listeningMode}
                  onChangeListeningMode={(m) => void handleChangeListeningMode(m)}
                  recentHeard={
                    recentHeard.length > 0 ? recentHeard : (voiceStatus?.recent_heard ?? [])
                  }
                  transcribing={transcribing}
                  micLevel={micLevel}
                  micError={micError}
                  assistantState={assistantState}
                  latestReply={latestReply}
                  streamingText={streamingText}
                  aiError={aiError}
                />
              </div>
            )}

            {drawerTab === "agents" && (
              <AgentsPanel
                latestAgentRun={latestAgentRun}
                onSpeakSummary={(summary) => {
                  appendLocalMessage("assistant", summary);
                  speakImmediate(summary);
                }}
              />
            )}
            {drawerTab === "vision" && (
              <VisionPanel
                cameraEnabled={cameraEnabled}
                cameraReady={cameraReady}
                cameraError={cameraError}
                stream={cameraStream}
                onToggleCamera={toggleCamera}
                captureFrameB64={captureFrameB64}
                onSpeakDescription={(desc) => {
                  appendLocalMessage("assistant", desc);
                  speakImmediate(desc);
                }}
              />
            )}
            {drawerTab === "projects" && <ProjectsPanel />}
            {drawerTab === "tasks" && <ProductivityPanel initialTab="tasks" />}
            {drawerTab === "agenda" && <ProductivityPanel initialTab="agenda" />}
            {drawerTab === "web" && <ProductivityPanel initialTab="web" />}
            {drawerTab === "system" && <SystemMonitorPanel system={currentSystem} />}
            {drawerTab === "memory" && <MemoryPanel />}
            {drawerTab === "tools" && <ToolsSecurityPanel />}
            {drawerTab === "conversations" && (
              <ConversationsPanel
                activeConversationId={activeConversationId}
                messages={messages}
                onSelectConversation={handleSelectConversation}
                onNewConversation={handleNewConversation}
              />
            )}
            {drawerTab === "settings" && (
              <AISettingsPanel
                onConfigUpdated={setAiProviders}
                onVoiceUpdated={setVoiceStatus}
                onTestVoice={() => void handleCoreClick()}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
