import type {
  ActionLogEntry,
  AgentProfileItem,
  AgentRunItem,
  AgendaEventItem,
  AIConfigUpdatePayload,
  AIProvidersResponse,
  AlertConfigData,
  ConversationSummary,
  DesktopStatusResponse,
  HealthResponse,
  MemoryItem,
  MemoryListResponse,
  NotificationsResponse,
  PendingApprovalItem,
  PersistedMessage,
  ProjectAnalysisReport,
  ProjectEntryItem,
  SystemSnapshot,
  TaskEntryItem,
  TelemetryHistoryPoint,
  ToolsListResponse,
  VisionStatusResponse,
  VoiceStatusResponse,
  WebSearchResultItem,
} from "../types/api";

const API_BASE = "/api/v1";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = `Erro HTTP ${response.status} ao consultar ${path}`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // Keep generic HTTP error message
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  getHealth: () => requestJson<HealthResponse>("/health"),
  getSystemStatus: () => requestJson<SystemSnapshot>("/system/status"),
  getAIProviders: () => requestJson<AIProvidersResponse>("/ai/providers"),
  updateAIConfig: (payload: AIConfigUpdatePayload) =>
    requestJson<AIProvidersResponse>("/ai/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getConversations: () => requestJson<ConversationSummary[]>("/conversations"),
  createConversation: (title: string) =>
    requestJson<ConversationSummary>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getMessages: (conversationId: number) =>
    requestJson<PersistedMessage[]>(`/conversations/${conversationId}/messages`),
  getVoiceStatus: () => requestJson<VoiceStatusResponse>("/voice/status"),
  updateVoiceConfig: (voice: string) =>
    requestJson<{ voice: string; available_voices: string[] }>("/voice/config", {
      method: "PUT",
      body: JSON.stringify({ voice }),
    }),
  synthesizeSpeech: async (text: string, voice?: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/voice/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
    if (!response.ok) {
      throw new Error(`Erro HTTP ${response.status} na síntese de voz.`);
    }
    return response.blob();
  },
  transcribeAudio: async (
    wavBlob: Blob,
    language = "pt",
  ): Promise<{ text: string; engine: string }> => {
    const formData = new FormData();
    formData.append("audio", wavBlob, "speech.wav");
    formData.append("language", language);

    const response = await fetch(`${API_BASE}/voice/transcribe`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      let detail = `Erro HTTP ${response.status} na transcrição de voz.`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        // Keep generic message
      }
      throw new Error(detail);
    }
    return response.json() as Promise<{ text: string; engine: string }>;
  },
  getTools: () => requestJson<ToolsListResponse>("/tools"),
  getActionLogs: (limit = 30) => requestJson<ActionLogEntry[]>(`/tools/logs?limit=${limit}`),
  getPendingApprovals: () => requestJson<PendingApprovalItem[]>("/tools/approvals"),
  approveAction: (approvalId: string) =>
    requestJson<{ status: string; tool: string; message: string }>(
      `/tools/approvals/${approvalId}/approve`,
      { method: "POST" },
    ),
  rejectAction: (approvalId: string) =>
    requestJson<{ status: string; approval_id: string; tool: string }>(
      `/tools/approvals/${approvalId}/reject`,
      { method: "POST" },
    ),
  startNativeVoice: () =>
    requestJson<Record<string, unknown>>("/voice/native/start", { method: "POST" }),
  stopNativeVoice: () =>
    requestJson<Record<string, unknown>>("/voice/native/stop", { method: "POST" }),
  updateNativeVoiceConfig: (requireWakeWord: boolean) =>
    requestJson<Record<string, unknown>>("/voice/native/config", {
      method: "PUT",
      body: JSON.stringify({ require_wake_word: requireWakeWord }),
    }),
  getSystemHistory: () =>
    requestJson<{ points: TelemetryHistoryPoint[] }>("/system/history"),
  getAlertConfig: () => requestJson<AlertConfigData>("/system/alerts/config"),
  updateAlertConfig: (payload: AlertConfigData) =>
    requestJson<AlertConfigData>("/system/alerts/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getNotifications: (limit = 30) =>
    requestJson<NotificationsResponse>(`/notifications?limit=${limit}`),
  markNotificationRead: (id: number) =>
    requestJson<{ id: number; read: boolean }>(`/notifications/${id}/read`, {
      method: "POST",
    }),
  markAllNotificationsRead: () =>
    requestJson<{ unread_count: number }>("/notifications/read-all", {
      method: "POST",
    }),
  getMemories: (category = "all", query = "") => {
    const params = new URLSearchParams();
    if (category && category !== "all") params.set("category", category);
    if (query.trim()) params.set("q", query.trim());
    const qs = params.toString();
    return requestJson<MemoryListResponse>(`/memory${qs ? `?${qs}` : ""}`);
  },
  createMemory: (category: string, content: string) =>
    requestJson<MemoryItem>("/memory", {
      method: "POST",
      body: JSON.stringify({ category, content, source: "user", approved: true }),
    }),
  updateMemory: (
    id: number,
    payload: { content?: string; category?: string; approved?: boolean },
  ) =>
    requestJson<MemoryItem>(`/memory/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteMemory: (id: number) =>
    requestJson<{ deleted: boolean; id: number }>(`/memory/${id}`, {
      method: "DELETE",
    }),
  getProjects: () => requestJson<ProjectEntryItem[]>("/projects"),
  createProject: (payload: { name: string; directory: string; description?: string }) =>
    requestJson<ProjectEntryItem>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  analyzeProject: (id: number) =>
    requestJson<{ project: ProjectEntryItem; report: ProjectAnalysisReport }>(
      `/projects/${id}/analyze`,
      { method: "POST" },
    ),
  deleteProject: (id: number) =>
    requestJson<{ deleted: boolean }>(`/projects/${id}`, { method: "DELETE" }),
  getTasks: () => requestJson<TaskEntryItem[]>("/tasks"),
  createTask: (title: string, priority = "medium") =>
    requestJson<TaskEntryItem>("/tasks", {
      method: "POST",
      body: JSON.stringify({ title, priority }),
    }),
  updateTaskStatus: (id: number, status: string) =>
    requestJson<TaskEntryItem>(`/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteTask: (id: number) =>
    requestJson<{ deleted: boolean }>(`/tasks/${id}`, { method: "DELETE" }),
  getAgenda: () => requestJson<AgendaEventItem[]>("/agenda"),
  createAgendaEvent: (title: string, startAt?: string) =>
    requestJson<AgendaEventItem>("/agenda", {
      method: "POST",
      body: JSON.stringify({ title, start_at: startAt || undefined }),
    }),
  deleteAgendaEvent: (id: number) =>
    requestJson<{ deleted: boolean }>(`/agenda/${id}`, { method: "DELETE" }),
  searchWeb: (q: string) =>
    requestJson<{ query: string; results: WebSearchResultItem[] }>(
      `/web/search?q=${encodeURIComponent(q)}`,
    ),
  getVisionStatus: () => requestJson<VisionStatusResponse>("/vision/status"),
  analyzeVision: (prompt: string, imageB64?: string) =>
    requestJson<{ description: string; model: string }>("/vision/analyze", {
      method: "POST",
      body: JSON.stringify({ prompt, image_b64: imageB64 }),
    }),
  setListeningMode: (mode: "proactive" | "always_reply" | "wake_word") =>
    requestJson<{ listening_mode: "proactive" | "always_reply" | "wake_word" }>("/voice/mode", {
      method: "PUT",
      body: JSON.stringify({ mode }),
    }),
  getAgents: () => requestJson<{ agents: AgentProfileItem[] }>("/agents"),
  getAgentRuns: (limit = 15) => requestJson<{ runs: AgentRunItem[] }>(`/agents/runs?limit=${limit}`),
  runAgent: (goal: string, agentType?: string) =>
    requestJson<AgentRunItem>("/agents/run", {
      method: "POST",
      body: JSON.stringify({
        goal,
        agent_type: agentType || undefined,
      }),
    }),
  getDesktopStatus: () => requestJson<DesktopStatusResponse>("/desktop/status"),
  setDesktopAutostart: (enabled: boolean) =>
    requestJson<DesktopStatusResponse>("/desktop/autostart", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  setDesktopNotifications: (enabled: boolean) =>
    requestJson<DesktopStatusResponse>("/desktop/notifications", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  installDesktopLauncher: () =>
    requestJson<DesktopStatusResponse>("/desktop/install-launcher", {
      method: "POST",
    }),
  sendTestDesktopNotification: () =>
    requestJson<{ sent: boolean; title: string; message: string }>("/desktop/notify", {
      method: "POST",
      body: JSON.stringify({
        title: "Arcanjo Desktop",
        message: "Notificações nativas do Ubuntu operacionais.",
        urgency: "normal",
      }),
    }),
};
