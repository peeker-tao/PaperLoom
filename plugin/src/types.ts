export type Scope = "selection" | "section" | "paper";
export type ReadMode = "original" | "translated" | "dual";
export type SidebarTab = "chat" | "notes" | "analysis";

export interface Selection {
  text: string;
  page: number;
  pageLabel?: string;
  rects?: number[][];
  kind?: "text" | "formula" | "figure";
  /** data:image/... base64 Data URL, only for figure annotations */
  image?: string;
}

export interface DocumentMeta {
  id: string;
  libraryId: string;
  itemKey: string;
  attachmentKey: string;
  fileHash: string;
  title: string;
  pages: number;
  alignment: "segment" | "page" | "none";
  alignmentNote: string;
  scanned: boolean;
  textChars: number;
}

export interface Segment {
  id: string;
  page: number;
  ordinal: number;
  text: string;
  translation: string | null;
  bbox: [number, number, number, number];
  kind: string;
  align: string;
}

export interface Citation {
  segmentId: string;
  marker?: string;
  documentId?: string;
  page: number;
  quote: string;
  bbox?: number[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  status: "streaming" | "done" | "failed" | "cancelled";
  model?: string;
  usage?: Usage;
}

export interface Usage {
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  estimated?: boolean;
  costUsd?: number;
}

export interface JobProgress {
  done: number;
  total: number;
  page?: number;
  message?: string;
}

export interface Job {
  id: string;
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "interrupted";
  stage: string;
  progress?: JobProgress;
  error?: { code: string; message: string; retryable: boolean } | null;
  usage?: Usage | null;
  artifacts?: { kind: string; path: string; bytes?: number }[];
  documentId?: string;
  options?: { pages?: number[] | null; model?: string | null; force?: boolean };
}

export interface Term {
  id: string;
  document_id: string | null;
  source: string;
  target: string;
  scope: "paper" | "global";
  status: "suggested" | "confirmed";
  note: string;
}

export interface ApiKeyStatus {
  configured: boolean;
  source: string;
  hint: string;
}

export interface ServiceStatus {
  version: string;
  apiVersion: number;
  dataDir: string;
  llm?: "live" | "fake";
  apiKey: ApiKeyStatus;
  capabilities: {
    babeldoc: { available: boolean; path: string; license: string };
    fts5: boolean;
    vision: boolean;
    alignment: string;
  };
  activeJobs: number;
}

export interface SettingsPayload {
  settings: {
    base_url: string;
    translate_model: string;
    chat_model: string;
    analysis_model: string;
    timeout_seconds: number;
    connect_timeout_seconds: number;
    concurrency: number;
    qps: number;
    max_retries: number;
    context_chars: number;
    max_output_tokens: number;
    thinking: boolean;
    babeldoc_enabled: boolean;
    baseUrlDefault: string;
  };
  apiKey: ApiKeyStatus;
  baseUrlCheck?: {
    ok: boolean;
    normalized: string;
    endpoint: string;
    sdkBase: string;
    message: string;
  };
  models: { id: string; label: string }[];
  service: { version: string; apiVersion: number };
}

export interface TranslationStatus {
  total: number;
  current: number;
  stale: number;
  unknown: number;
  missing: number;
  reasons: string[];
  reasonsText: string[];
  staleSegmentIds: string[];
  configKey: string;
  needsAttention: boolean;
}

export interface ReadingState {
  page: number;
  mode: ReadMode;
  sidebar_width: number;
  sidebar_open: number;
}

export interface AttachmentContext {
  attachmentItemID: number;
  parentItemID: number | null;
  libraryID: number;
  attachmentKey: string;
  itemKey: string;
  title: string;
  pdfPath: string;
}

export interface SSEEvent {
  event: string;
  data: any;
}
