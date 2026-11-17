export function debug(...parts: unknown[]): void {
  try {
    const text = parts
      .map((part) => (typeof part === "string" ? part : JSON.stringify(part)))
      .join(" ");
    (globalThis as any).Zotero?.debug(`PaperLoom: ${text}`);
  } catch {
    // Logging must never break the plugin.
  }
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
