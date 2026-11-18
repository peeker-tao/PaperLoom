/** Lines buffered for the "服务诊断" panel and the on-disk plugin log. */
const LOG_BUFFER_SIZE = 120;

export type LogSink = (lines: string[]) => void;

const buffer: string[] = [];
let sink: LogSink | null = null;
let pending: string[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function stamp(): string {
  return new Date().toISOString().slice(11, 23);
}

function format(parts: unknown[]): string {
  return parts
    .map((part) => {
      if (typeof part === "string") {
        return part;
      }
      if (part instanceof Error) {
        return `${part.name}: ${part.message}`;
      }
      try {
        return JSON.stringify(part);
      } catch {
        return String(part);
      }
    })
    .join(" ");
}

/**
 * Records a diagnostic line.
 *
 * `Zotero.debug` is not reachable from the reader iframe — which is exactly
 * where the sidebar runs — so logging through it silently produced nothing, and
 * a button that failed left no trace anywhere. Lines are buffered in memory
 * (shown in "服务诊断") and, once a sink is registered, sent to the service log
 * file, which outlives the session.
 */
export function debug(...parts: unknown[]): void {
  const text = `${stamp()} ${format(parts)}`;
  buffer.push(text);
  if (buffer.length > LOG_BUFFER_SIZE) {
    buffer.shift();
  }
  try {
    (globalThis as any).Zotero?.debug?.(`PaperLoom: ${text}`);
  } catch {
    // Logging must never break the plugin.
  }
  pending.push(text);
  if (!sink || flushTimer) {
    return;
  }
  // Batched: a burst of log lines must not become a burst of HTTP requests.
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flush();
  }, 1500);
}

/** Ship buffered lines to the service; safe to call at any time. */
export function flush(): void {
  if (!sink || !pending.length) {
    return;
  }
  const lines = pending;
  pending = [];
  try {
    sink(lines);
  } catch {
    // The diagnostics panel still has the in-memory buffer.
  }
}

export function setLogSink(next: LogSink | null): void {
  sink = next;
}

/** Most recent lines, oldest first. */
export function recentLogs(limit = 60): string[] {
  return buffer.slice(-limit);
}

/** Record uncaught UI errors instead of letting them vanish. */
export function installErrorReporting(win: any): void {
  if (!win || win.__paperloomErrorHooks) {
    return;
  }
  win.__paperloomErrorHooks = true;
  win.addEventListener?.("error", (event: any) => {
    debug("window.onerror", event?.message || "", event?.lineno || 0);
  });
  win.addEventListener?.("unhandledrejection", (event: any) => {
    const reason = event?.reason;
    debug("unhandledrejection", reason instanceof Error ? reason.message : String(reason));
  });
}

export function errorText(error: unknown): string {
  if (!error) {
    return "未知错误";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
