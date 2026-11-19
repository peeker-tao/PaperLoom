/**
 * Choosing which model a chat request runs on.
 *
 * The model selection is a user preference, but it must never point at a model
 * the service does not offer: an unknown id is rejected by the provider with a
 * 400 that reads like a network problem. Keeping the resolution rule in one
 * pure function makes it testable without Zotero, and gives one place to change
 * if the list of supported models is ever discovered at runtime.
 */

export interface ModelOption {
  id: string;
  label: string;
}

/**
 * Pick the model to use for the next chat request.
 *
 * Order:
 *   1. The saved selection, but only if the service still offers it. A model can
 *      disappear when the service is upgraded or the provider retires it, and a
 *      stale preference must not wedge every question.
 *   2. The document/service default (`settings.chat_model`).
 *   3. The first offered model, so the picker is never empty.
 */
export function resolveChatModel(
  saved: string | undefined | null,
  models: ModelOption[] | undefined | null,
  fallback: string | undefined | null,
): string {
  const offered = (models || []).map((model) => model.id);
  const candidate = String(saved || "").trim();
  if (candidate && (!offered.length || offered.includes(candidate))) {
    return candidate;
  }
  const defaulted = String(fallback || "").trim();
  if (defaulted && (!offered.length || offered.includes(defaulted))) {
    return defaulted;
  }
  return offered[0] || defaulted || "";
}

/** True when `model` is one the service offers (always true for an empty list). */
export function isKnownModel(model: string, models: ModelOption[] | undefined | null): boolean {
  if (!model) {
    return false;
  }
  const offered = (models || []).map((item) => item.id);
  return !offered.length || offered.includes(model);
}

/**
 * Label for the sidebar picker.
 *
 * "deepseek-v4-pro" alone says nothing about what was selected, so the label
 * from the service is preferred and the scope is stated: this select only
 * changes the Q&A model, not translation or analysis.
 */
export function modelLabel(model: string, models: ModelOption[] | undefined | null): string {
  const found = (models || []).find((item) => item.id === model);
  return found?.label || model || "默认模型";
}
