import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentRunItem,
  AmbientHeardItem,
  AssistantState,
  ChatMessageItem,
  FaceMood,
  ListeningMode,
  NotificationItem,
  PendingApprovalItem,
  SystemSnapshot,
} from "../types/api";
import type { JarvisEvent } from "../types/events";

interface UseJarvisSocketOptions {
  onStreamStart?: () => void;
  onStreamDelta?: (delta: string) => void;
  onStreamEnd?: (fullText: string, spokenNatively?: boolean) => void;
  onNotification?: (item: NotificationItem) => void;
  onVisionCaptureRequest?: (requestId: string) => void;
}

interface UseJarvisSocketResult {
  connected: boolean;
  assistantState: AssistantState;
  faceMood: FaceMood;
  systemUpdate: SystemSnapshot | null;
  messages: ChatMessageItem[];
  latestReply: ChatMessageItem | null;
  streamingText: string;
  activeConversationId: number | null;
  activeProviderLabel: string | null;
  aiError: string | null;
  streamPulse: number;
  pendingApprovals: PendingApprovalItem[];
  activeToolLabel: string | null;
  activeAgentLabel: string | null;
  latestAgentRun: AgentRunItem | null;
  nativeWindowActive: boolean;
  recentHeard: AmbientHeardItem[];
  listeningMode: ListeningMode;
  setActiveConversationId: (id: number | null) => void;
  setMessages: (items: ChatMessageItem[]) => void;
  removePendingApproval: (approvalId: string) => void;
  clearError: () => void;
  sendCommand: (message: Record<string, unknown>) => void;
  appendLocalMessage: (role: "user" | "assistant" | "system", content: string) => void;
}

export function useJarvisSocket(
  options: UseJarvisSocketOptions = {},
): UseJarvisSocketResult {
  const [connected, setConnected] = useState(false);
  const [assistantState, setAssistantState] = useState<AssistantState>("idle");
  const [faceMood, setFaceMood] = useState<FaceMood>("neutral");
  const [systemUpdate, setSystemUpdate] = useState<SystemSnapshot | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [latestReply, setLatestReply] = useState<ChatMessageItem | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [activeProviderLabel, setActiveProviderLabel] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [streamPulse, setStreamPulse] = useState(0);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApprovalItem[]>([]);
  const [activeToolLabel, setActiveToolLabel] = useState<string | null>(null);
  const [activeAgentLabel, setActiveAgentLabel] = useState<string | null>(null);
  const [latestAgentRun, setLatestAgentRun] = useState<AgentRunItem | null>(null);
  const [nativeWindowActive, setNativeWindowActive] = useState(false);
  const [recentHeard, setRecentHeard] = useState<AmbientHeardItem[]>([]);
  const [listeningMode, setListeningMode] = useState<ListeningMode>("proactive");
  const wsRef = useRef<WebSocket | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const appendLocalMessage = useCallback(
    (role: "user" | "assistant" | "system", content: string) => {
      const item: ChatMessageItem = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role,
        content,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev.slice(-49), item]);
      if (role === "assistant") {
        setLatestReply(item);
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    let reconnectTimer: number | undefined;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        if (!active) return;
        setConnected(true);
        socket.send(JSON.stringify({ type: "system.request" }));
      };

      socket.onmessage = (event) => {
        if (!active) return;
        try {
          const parsed = JSON.parse(event.data) as JarvisEvent;

          if (parsed.type === "connection.ready" && typeof parsed.payload.state === "string") {
            setAssistantState(parsed.payload.state as AssistantState);
          } else if (
            parsed.type === "assistant.mood" &&
            typeof parsed.payload.mood === "string"
          ) {
            setFaceMood(parsed.payload.mood as FaceMood);
          } else if (parsed.type.startsWith("assistant.")) {
            const state = parsed.type.replace("assistant.", "") as AssistantState;
            setAssistantState(state);
            if (state === "idle") {
              setStreamingText("");
              setActiveToolLabel(null);
            }
          } else if (parsed.type === "system.updated") {
            setSystemUpdate(parsed.payload as unknown as SystemSnapshot);
          } else if (parsed.type === "notification.created") {
            optionsRef.current.onNotification?.(
              parsed.payload as unknown as NotificationItem,
            );
          } else if (parsed.type === "tool.started" && typeof parsed.payload.tool === "string") {
            setActiveToolLabel(`A executar: ${parsed.payload.tool}`);
          } else if (parsed.type === "tool.completed" || parsed.type === "tool.failed") {
            setActiveToolLabel(null);
          } else if (parsed.type === "agent.started" && typeof parsed.payload.agent_name === "string") {
            setActiveAgentLabel(`Missão: ${parsed.payload.agent_name}`);
          } else if (parsed.type === "agent.step" && typeof parsed.payload.agent_type === "string") {
            const stepInfo = parsed.payload.step as { action?: string } | undefined;
            if (stepInfo?.action) {
              setActiveAgentLabel(`Agente (${parsed.payload.agent_type}): ${stepInfo.action}`);
            }
          } else if (parsed.type === "agent.completed") {
            setActiveAgentLabel(null);
            setLatestAgentRun(parsed.payload as unknown as AgentRunItem);
          } else if (parsed.type === "tool.approval_required") {
            const item = parsed.payload as unknown as PendingApprovalItem;
            setPendingApprovals((prev) =>
              prev.some((p) => p.approval_id === item.approval_id) ? prev : [...prev, item],
            );
          } else if (
            parsed.type === "tool.rejected" &&
            typeof parsed.payload.approval_id === "string"
          ) {
            setPendingApprovals((prev) =>
              prev.filter((p) => p.approval_id !== parsed.payload.approval_id),
            );
          } else if (
            parsed.type === "vision.capture_request" &&
            typeof parsed.payload.request_id === "string"
          ) {
            optionsRef.current.onVisionCaptureRequest?.(parsed.payload.request_id);
          } else if (parsed.type === "chat.stream.start") {
            setAiError(null);
            setStreamingText("");
            optionsRef.current.onStreamStart?.();
            if (typeof parsed.payload.conversation_id === "number") {
              setActiveConversationId(parsed.payload.conversation_id);
            }
            if (
              typeof parsed.payload.provider === "string" &&
              typeof parsed.payload.model === "string"
            ) {
              setActiveProviderLabel(`${parsed.payload.provider} · ${parsed.payload.model}`);
            }
          } else if (parsed.type === "chat.stream.delta" && typeof parsed.payload.delta === "string") {
            const delta = parsed.payload.delta;
            setStreamingText((prev) => prev + delta);
            setStreamPulse(0.55 + Math.random() * 0.45);
            optionsRef.current.onStreamDelta?.(delta);
          } else if (parsed.type === "voice.native.transcript") {
            if (typeof parsed.payload.cleaned === "string" && parsed.payload.cleaned) {
              appendLocalMessage("user", parsed.payload.cleaned);
            }
            if (typeof parsed.payload.window_active === "boolean") {
              setNativeWindowActive(parsed.payload.window_active);
            }
          } else if (parsed.type === "voice.native.status") {
            if (typeof parsed.payload.window_active === "boolean") {
              setNativeWindowActive(parsed.payload.window_active);
            }
            if (
              parsed.payload.listening_mode === "proactive" ||
              parsed.payload.listening_mode === "always_reply" ||
              parsed.payload.listening_mode === "wake_word"
            ) {
              setListeningMode(parsed.payload.listening_mode);
            }
          } else if (parsed.type === "voice.ambient.heard") {
            if (Array.isArray(parsed.payload.recent_heard)) {
              setRecentHeard(parsed.payload.recent_heard as AmbientHeardItem[]);
            }
            if (
              parsed.payload.mode === "proactive" ||
              parsed.payload.mode === "always_reply" ||
              parsed.payload.mode === "wake_word"
            ) {
              setListeningMode(parsed.payload.mode);
            }
            if (typeof parsed.payload.mood === "string") {
              setFaceMood(parsed.payload.mood as FaceMood);
            }
          } else if (parsed.type === "chat.stream.end" && typeof parsed.payload.content === "string") {
            setStreamingText("");
            setStreamPulse(0);
            if (typeof parsed.payload.conversation_id === "number") {
              setActiveConversationId(parsed.payload.conversation_id);
            }
            if (typeof parsed.payload.mood === "string") {
              setFaceMood(parsed.payload.mood as FaceMood);
            }
            appendLocalMessage("assistant", parsed.payload.content);
            optionsRef.current.onStreamEnd?.(
              parsed.payload.content,
              Boolean(parsed.payload.spoken_natively),
            );
          } else if (parsed.type === "chat.error" && typeof parsed.payload.message === "string") {
            setStreamingText("");
            setStreamPulse(0);
            setAiError(parsed.payload.message);
          }
        } catch {
          // Ignore malformed JSON frames
        }
      };

      socket.onclose = () => {
        if (!active) return;
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      active = false;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [appendLocalMessage]);

  const sendCommand = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const removePendingApproval = useCallback((approvalId: string) => {
    setPendingApprovals((prev) => prev.filter((p) => p.approval_id !== approvalId));
  }, []);

  const clearError = useCallback(() => setAiError(null), []);

  return {
    connected,
    assistantState,
    faceMood,
    systemUpdate,
    messages,
    latestReply,
    streamingText,
    activeConversationId,
    activeProviderLabel,
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
  };
}
