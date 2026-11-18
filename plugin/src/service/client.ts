import type { SSEEvent } from "../types";

export class ServiceError extends Error {
  status: number;
  code: string;
  retryable: boolean;

  constructor(message: string, status = 0, code = "network", retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

export interface Endpoint {
  baseUrl: string;
  token: string;
}

export class ServiceClient {
  constructor(private readonly endpoint: () => Endpoint | null) {}

  private require(): Endpoint {
    const endpoint = this.endpoint();
    if (!endpoint) {
      throw new ServiceError("本地服务未启动", 0, "service_down", true);
    }
    return endpoint;
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const { token } = this.require();
    return {
      "Content-Type": "application/json",
      "X-PaperLoom-Token": token,
      ...extra,
    };
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const { baseUrl } = this.require();
    const response = await this.fetchOrExplain(`${baseUrl}${path}`, {
      ...init,
      headers: this.headers((init.headers as Record<string, string>) || {}),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return (await response.json()) as T;
  }

  /**
   * `fetch` that turns "nothing is listening" into an actionable message.
   *
   * It rejects with an opaque TypeError when the service is not running. Report
   * that raw and the user sees "NetworkError when attempting to fetch resource",
   * which is exactly what a crashed service looks like: the port was cached from
   * the last successful `/health`, so `require()` cannot notice the process is
   * gone. Every call — including 翻译 — then failed with that unhelpful text.
   */
  private async fetchOrExplain(url: string, init: RequestInit): Promise<Response> {
    try {
      return await fetch(url, init);
    } catch (error) {
      if (error instanceof ServiceError) {
        throw error;
      }
      throw new ServiceError(
        "本地服务无响应。请确认 PaperLoom 服务正在运行（设置 → 自检 可查看端口）。",
        0,
        "service_down",
        true,
      );
    }
  }

  private async toError(response: Response): Promise<ServiceError> {
    let message = `HTTP ${response.status}`;
    let code = "http";
    let retryable = false;
    try {
      const body = await response.json();
      const detail = body?.detail ?? body;
      message = detail?.message || detail?.detail || message;
      code = detail?.code || code;
      retryable = Boolean(detail?.retryable);
    } catch {
      // Non-JSON error body.
    }
    return new ServiceError(message, response.status, code, retryable);
  }

  /**
   * Send diagnostic lines to the service log.
   *
   * Fire and forget: logging must never fail a user action, and there is no
   * point retrying — the next line will report the failure anyway.
   */
  clientLog(lines: string[], source = "plugin"): void {
    const endpoint = this.endpoint();
    if (!endpoint || !lines.length) {
      return;
    }
    try {
      void fetch(`${endpoint.baseUrl}/v1/client-log`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-PaperLoom-Token": endpoint.token,
        },
        body: JSON.stringify({ lines, source }),
      }).catch(() => undefined);
    } catch {
      // Byte-level failure; nothing useful to do from a logger.
    }
  }

  /**
   * Fetch a rendered page image from the service.
   *
   * Preferred over rendering in the reader: the sidebar has no reliable access
   * to the reader's pdf.js instance, and when that path failed the reading view
   * showed "图片需要回到 PDF 查看" — a missing feature from the user's side.
   */
  async pageImage(
    documentId: string,
    page: number,
    options: { width?: number; bbox?: number[] } = {},
  ): Promise<Blob> {
    const { baseUrl } = this.require();
    const params = new URLSearchParams({
      width: String(Math.round(options.width || 1400)),
    });
    if (options.bbox && options.bbox.length === 4) {
      params.set("bbox", options.bbox.map((value) => Number(value) || 0).join(","));
    }
    const response = await this.fetchOrExplain(
      `${baseUrl}/v1/documents/${encodeURIComponent(documentId)}/page/${page}.png?${params.toString()}`,
      { headers: this.headers() },
    );
    if (!response.ok) {
      throw await this.toError(response);
    }
    return await response.blob();
  }

  async *stream(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
    const { baseUrl } = this.require();
    const response = await this.fetchOrExplain(`${baseUrl}${path}`, {
      method: "POST",
      headers: this.headers({ Accept: "text/event-stream" }),
      body: JSON.stringify(body),
      signal,
    });
    if (!response.ok || !response.body) {
      throw await this.toError(response);
    }
    yield* this.consume(response);
  }

  async *getStream(path: string, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
    const { baseUrl } = this.require();
    const response = await fetch(`${baseUrl}${path}`, {
      headers: this.headers({ Accept: "text/event-stream" }),
      signal,
    });
    if (!response.ok || !response.body) {
      throw await this.toError(response);
    }
    yield* this.consume(response);
  }

  private async *consume(response: Response): AsyncGenerator<SSEEvent> {
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        let index = buffer.indexOf("\n\n");
        while (index >= 0) {
          const raw = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          const parsed = parseEvent(raw);
          if (parsed) {
            yield parsed;
          }
          index = buffer.indexOf("\n\n");
        }
      }
      const tail = parseEvent(buffer);
      if (tail) {
        yield tail;
      }
    } finally {
      try {
        reader.releaseLock();
      } catch {
        // Already released on abort.
      }
    }
  }

  // ---- endpoints ----------------------------------------------------- //
  health(): Promise<{ ok: boolean; service: string; version: string; apiVersion: number }> {
    return this.request("/health");
  }

  status() {
    return this.request<import("../types").ServiceStatus>("/v1/status");
  }

  getSettings() {
    return this.request<import("../types").SettingsPayload>("/v1/settings");
  }

  saveSettings(patch: Record<string, unknown>) {
    return this.request<{ settings: any; apiKey: import("../types").ApiKeyStatus }>("/v1/settings", {
      method: "POST",
      body: JSON.stringify(patch),
    });
  }

  testSettings(model?: string) {
    return this.request<{ ok: boolean; error?: any; latencyMs?: number; reply?: string }>(
      "/v1/settings/test",
      { method: "POST", body: JSON.stringify({ model }) },
    );
  }

  registerDocument(payload: Record<string, unknown>) {
    return this.request<{
      document: import("../types").DocumentMeta;
      segmentCount: number;
      cached: boolean;
      coverage?: number;
      /** True when an older segmentation was rebuilt (former translations are void). */
      reparsed?: boolean;
    }>("/v1/documents/register", { method: "POST", body: JSON.stringify(payload) });
  }

  getDocument(documentId: string) {
    return this.request<{ document: import("../types").DocumentMeta; segmentCount: number; translatedCount: number }>(
      `/v1/documents/${documentId}`,
    );
  }

  getSegments(documentId: string, page?: number) {
    const query = page ? `?page=${page}` : "";
    return this.request<{ segments: import("../types").Segment[]; count: number }>(
      `/v1/documents/${documentId}/segments${query}`,
    );
  }

  /** Whole document as Markdown (English first, Chinese after). */
  getMarkdown(
    documentId: string,
    options: { original?: boolean; translation?: boolean; pages?: boolean; references?: boolean } = {},
  ) {
    const params = new URLSearchParams();
    if (options.original === false) {
      params.set("original", "false");
    }
    if (options.translation === false) {
      params.set("translation", "false");
    }
    if (options.pages === false) {
      params.set("pages", "false");
    }
    if (options.references) {
      params.set("references", "true");
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<{
      markdown: string;
      filename: string;
      stats: { chars: number; bytes: number; englishWords: number; chineseChars: number; segments: number };
    }>(`/v1/documents/${documentId}/markdown${query}`);
  }

  startTranslation(documentId: string, options: Record<string, unknown> = {}) {
    return this.request<{ job: import("../types").Job }>("/v1/jobs", {
      method: "POST",
      body: JSON.stringify({ documentId, ...options }),
    });
  }

  translationStatus(documentId: string, model?: string) {
    const query = model ? `?model=${encodeURIComponent(model)}` : "";
    return this.request<import("../types").TranslationStatus>(
      `/v1/documents/${documentId}/translation-status${query}`,
    );
  }

  listJobs(documentId: string, limit = 5) {
    return this.request<{ jobs: import("../types").Job[] }>(
      `/v1/jobs?documentId=${encodeURIComponent(documentId)}&limit=${limit}`,
    );
  }

  cancelJob(jobId: string) {
    return this.request<{ job: import("../types").Job }>(`/v1/jobs/${jobId}/cancel`, { method: "POST" });
  }

  retryJob(jobId: string) {
    return this.request<{ job: import("../types").Job }>(`/v1/jobs/${jobId}/retry`, { method: "POST" });
  }

  jobEventsUrl(jobId: string, after: number) {
    return `/v1/jobs/${jobId}/events?after=${after}`;
  }

  chat(body: unknown, signal?: AbortSignal) {
    return this.stream("/v1/chat", body, signal);
  }

  analysis(body: unknown, signal?: AbortSignal) {
    return this.stream("/v1/analysis", body, signal);
  }

  async downloadArtifact(jobId: string, kind: string): Promise<ArrayBuffer> {
    const { baseUrl } = this.require();
    const response = await fetch(`${baseUrl}/v1/jobs/${jobId}/artifacts/${kind}`, {
      headers: { "X-PaperLoom-Token": this.require().token },
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.arrayBuffer();
  }

  getGlossary(documentId: string) {
    return this.request<{ terms: import("../types").Term[] }>(
      `/v1/glossary?documentId=${encodeURIComponent(documentId)}`,
    );
  }

  addTerm(body: Record<string, unknown>) {
    return this.request<{ term: import("../types").Term; affectedSegments: number }>("/v1/glossary", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  patchTerm(termId: string, body: Record<string, unknown>) {
    return this.request<{ term: import("../types").Term }>(`/v1/glossary/${termId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  deleteTerm(termId: string) {
    return this.request<{ deleted: boolean }>(`/v1/glossary/${termId}`, { method: "DELETE" });
  }

  extractTerms(documentId: string) {
    return this.request<{ terms: import("../types").Term[]; count: number }>("/v1/glossary/extract", {
      method: "POST",
      body: JSON.stringify({ documentId }),
    });
  }

  getReading(documentId: string) {
    return this.request<{ state: Partial<import("../types").ReadingState> }>(`/v1/reading/${documentId}`);
  }

  saveReading(documentId: string, body: Record<string, unknown>) {
    return this.request<{ state: import("../types").ReadingState }>(`/v1/reading/${documentId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  listConversations(documentId: string) {
    return this.request<{ conversations: { id: string; document_id: string; title: string; updated_at: number }[] }>(
      `/v1/conversations?documentId=${encodeURIComponent(documentId)}`,
    );
  }

  getMessages(conversationId: string) {
    return this.request<{ messages: any[] }>(`/v1/conversations/${conversationId}/messages`);
  }

  listAnalyses(documentId: string, limit = 5) {
    return this.request<{ analyses: any[] }>(
      `/v1/analyses?documentId=${encodeURIComponent(documentId)}&limit=${limit}`,
    );
  }

  search(documentId: string, query: string, limit = 8) {
    return this.request<{ hits: { segment_id: string; page: number; snippet: string }[] }>("/v1/search", {
      method: "POST",
      body: JSON.stringify({ documentId, query, limit }),
    });
  }
}

function parseEvent(raw: string): SSEEvent | null {
  const lines = raw.split("\n");
  let event = "message";
  const data: string[] = [];
  for (const line of lines) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trim());
    }
  }
  if (!data.length) {
    return null;
  }
  try {
    return { event, data: JSON.parse(data.join("\n")) };
  } catch {
    return { event, data: { raw: data.join("\n") } };
  }
}
