export type AssistantState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "executing"
  | "error";

export interface MusicState {
  playing: boolean;
  bpm: number;
  energy: number;
}

export type FaceMood =
  | "neutral"
  | "happy"
  | "sad"
  | "tired"
  | "curious"
  | "thinking"
  | "surprised";

export type NavSection =
  | "Dashboard"
  | "Assistente"
  | "Conversas"
  | "Projetos"
  | "Programação"
  | "Sistema"
  | "Ficheiros"
  | "Internet"
  | "Agenda"
  | "Tarefas"
  | "Memória"
  | "Automações"
  | "Configurações";

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status?: string;
}

export interface HealthResponse {
  status: "operational" | "degraded";
  app: string;
  version: string;
  environment: string;
  assistant_state: AssistantState;
  websocket_clients: number;
  database: {
    connected: boolean;
    engine: string;
  };
  ollama: {
    available: boolean;
    models: string[];
  };
  timestamp: string;
}

export interface SystemSnapshot {
  hostname: string;
  platform: string;
  platform_release: string;
  architecture: string;
  cpu_cores: number;
  cpu_percent: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_available_gb: number;
  ram_percent: number;
  disk_total_gb: number;
  disk_used_gb: number;
  disk_free_gb: number;
  disk_percent: number;
  net_rx_kbps?: number;
  net_tx_kbps?: number;
  uptime_seconds: number;
  temperature_celsius: number | null;
  battery_percent: number | null;
  battery_plugged: boolean | null;
  network_connected: boolean;
  top_processes?: ProcessInfo[];
}

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
}

export interface AIProviderInfo {
  name: string;
  kind: "local" | "external";
  available: boolean;
  configured: boolean;
  default_model: string;
  models: string[];
  detail: string;
}

export interface AIProvidersResponse {
  default_provider: string;
  fallback_provider: string;
  providers: AIProviderInfo[];
}

export interface AIConfigUpdatePayload {
  default_provider?: string;
  fallback_provider?: string;
  model?: string;
}

export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface PersistedMessage {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface VoiceStatusResponse {
  available: boolean;
  engine: string;
  model: string;
  voice: string;
  available_voices: string[];
  language: string;
  stt_available?: boolean;
  stt_engine?: string;
  neural_vad_available?: boolean;
  native_listening?: boolean;
  native_supported?: boolean;
  native_signal_detected?: boolean;
  listening_mode?: ListeningMode;
  require_wake_word?: boolean;
  window_active?: boolean;
  wake_word?: string;
  recent_heard?: AmbientHeardItem[];
}

export type ListeningMode = "proactive" | "always_reply" | "wake_word";

export interface AmbientHeardItem {
  speaker: string;
  text: string;
  time: string;
  source: string;
}

export interface ToolSummary {
  name: string;
  description: string;
  parameters_hint: string;
  permission_level: number;
}

export interface ToolsListResponse {
  tools: ToolSummary[];
  allowed_directories: string[];
  require_confirmation_level_2: boolean;
}

export interface PendingApprovalItem {
  approval_id: string;
  tool: string;
  target: string;
  description: string;
  permission_level: number;
  params: Record<string, unknown>;
}

export interface ActionLogEntry {
  id: number;
  action_type: string;
  target: string;
  permission_level: number;
  status: string;
  details: string;
  created_at: string;
}

export interface TelemetryHistoryPoint {
  timestamp: string;
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
  net_rx_kbps: number;
  net_tx_kbps: number;
  temperature_celsius: number | null;
}

export interface AlertConfigData {
  enabled: boolean;
  cpu_threshold: number;
  ram_threshold: number;
  disk_threshold: number;
  temp_threshold: number;
  cooldown_seconds: number;
}

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  severity: "info" | "warning" | "critical" | string;
  source: string;
  read: boolean;
  created_at: string;
}

export interface NotificationsResponse {
  unread_count: number;
  items: NotificationItem[];
}

export interface MemoryItem {
  id: number;
  category: "long_term" | "project" | "preference" | "operational" | string;
  content: string;
  source: string;
  approved: boolean;
  created_at: string;
  updated_at: string;
}

export interface OperationalMemoryItem {
  id: number;
  action_type: string;
  target: string;
  permission_level: number;
  status: string;
  created_at: string;
}

export interface MemoryListResponse {
  items: MemoryItem[];
  operational: OperationalMemoryItem[];
}

export interface ProjectEntryItem {
  id: number;
  name: string;
  description: string;
  directory: string;
  technologies: string;
  status: string;
  git_repo: string;
  last_activity_at: string;
  created_at: string;
}

export interface ProjectAnalysisReport {
  directory: string;
  total_files_scanned: number;
  top_extensions: Record<string, number>;
  technologies: string[];
  dependencies: string[];
  git: {
    initialized: boolean;
    status: string;
    recent_commits: string[];
  };
  issues: string[];
  recommendations: string[];
}

export interface TaskEntryItem {
  id: number;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "done" | string;
  priority: "low" | "medium" | "high" | string;
  created_at: string;
}

export interface AgendaEventItem {
  id: number;
  title: string;
  description: string;
  start_at: string;
}

export interface WebSearchResultItem {
  title: string;
  url: string;
  snippet: string;
}

export interface VisionStatusResponse {
  vision_ai_available: boolean;
  model: string;
  local_cameras: string[];
  ffmpeg_available: boolean;
  browser_camera_connected: boolean;
  any_camera_ready: boolean;
}

export type AgentType = "coding" | "system" | "research" | "automation" | "project";

export interface AgentProfileItem {
  id: AgentType;
  name: string;
  role: string;
  description: string;
  allowed_tools: string[];
}

export interface AgentStepItem {
  step: number;
  action: string;
  status: string;
  detail: string;
}

export interface AgentRunItem {
  id: number;
  agent_type: AgentType | string;
  agent_name: string;
  goal: string;
  status: "running" | "awaiting_confirmation" | "completed" | "failed" | string;
  steps: AgentStepItem[];
  summary: string;
  created_at: string;
  completed_at: string | null;
}

export interface DesktopStatusResponse {
  notify_send_available: boolean;
  desktop_notifications_enabled: boolean;
  autostart_enabled: boolean;
  autostart_path: string;
  desktop_entry_installed: boolean;
  desktop_entry_path: string;
  frontend_dist_ready: boolean;
  launch_script: string;
}
