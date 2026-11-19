/**
 * Reading the text the user has just selected inside the sidebar.
 *
 * The plugin already had a way to turn a selection into a question — the Zotero
 * selection popup in the PDF, and a toolbar over the page overlay. Neither
 * covered the place people actually read: the reflowed text in the sidebar. The
 * overlay's handler read `reader._iframeWindow.document.getSelection()`, which
 * cannot see a selection made inside the sidebar's shadow root at all, so
 * selecting a paragraph there did nothing whatsoever.
 *
 * The logic lives here, apart from React, so the edge cases can be tested: an
 * IME composition, a selection that crosses two paragraphs, a selection made
 * inside the composer's own textarea.
 */

export interface SelectionRect {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface SelectionHit {
  text: string;
  /** The paragraph the selection starts in, when it can be identified. */
  segmentId: string | null;
  /** Viewport coordinates, for placing a floating toolbar. */
  rect: SelectionRect | null;
}

/** Minimal shape of a DOM `Selection`; keeps this file testable without a DOM. */
export interface SelectionLike {
  isCollapsed?: boolean;
  rangeCount?: number;
  toString(): string;
  anchorNode?: Node | null;
  getRangeAt?(index: number): { getBoundingClientRect?(): SelectionRect };
}

/** A selection shorter than this is almost always a stray click. */
export const MIN_SELECTION_CHARS = 2;
/** Long selections are truncated: they cost tokens and are rarely intended. */
export const MAX_SELECTION_CHARS = 1200;

export function clampSelectionText(text: string, limit = MAX_SELECTION_CHARS): string {
  const flat = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (flat.length <= limit) {
    return flat;
  }
  return `${flat.slice(0, limit)}…`;
}

/**
 * Whether a node belongs to something the user is typing into.
 *
 * Selecting inside the composer is normal editing, not a request to ask about
 * it — without this check, highlighting a word to fix a typo would pop up a
 * "解释 / 提问" toolbar over the input.
 */
export function isEditableNode(node: Node | null | undefined): boolean {
  let current: any = node;
  let guard = 0;
  while (current && guard < 40) {
    guard += 1;
    const tag = String(current.tagName || "").toLowerCase();
    if (tag === "textarea" || tag === "input" || tag === "select") {
      return true;
    }
    if (current.isContentEditable === true) {
      return true;
    }
    // Walk up through shadow boundaries too, so a selection inside a nested
    // component is still attributed to its host.
    current = current.parentNode || current.host || null;
  }
  return false;
}

/** The nearest ancestor (or self) carrying `data-segment-id`. */
export function segmentIdOf(node: Node | null | undefined): string | null {
  let current: any = node;
  let guard = 0;
  while (current && guard < 40) {
    guard += 1;
    const direct = current.dataset?.segmentId;
    if (typeof direct === "string" && direct) {
      return direct;
    }
    if (typeof current.getAttribute === "function") {
      const attr = current.getAttribute("data-segment-id");
      if (attr) {
        return attr;
      }
    }
    current = current.parentNode || current.host || null;
  }
  return null;
}

/**
 * Turn a live selection into something the controller can use, or null.
 *
 * Returns null for a collapsed selection (a plain click), for a selection that
 * lives in a form field, and for one that is only punctuation — each of those is
 * a case where showing a toolbar would be noise.
 */
export function readSelectionFrom(source: SelectionLike | null | undefined): SelectionHit | null {
  if (!source) {
    return null;
  }
  if (source.isCollapsed) {
    return null;
  }
  if (typeof source.rangeCount === "number" && source.rangeCount === 0) {
    return null;
  }
  const text = clampSelectionText(source.toString());
  if (text.length < MIN_SELECTION_CHARS) {
    return null;
  }
  // `…`-only results come from an empty range inside a text node; treat as empty.
  if (!/[\p{L}\p{N}]/u.test(text)) {
    return null;
  }
  if (isEditableNode(source.anchorNode)) {
    return null;
  }
  let rect: SelectionRect | null = null;
  try {
    const range = source.getRangeAt?.(0);
    const box = range?.getBoundingClientRect?.();
    if (box && Number.isFinite(box.top) && Number.isFinite(box.left)) {
      rect = { top: box.top, bottom: box.bottom, left: box.left, right: box.right };
    }
  } catch {
    // A range can become stale between the event and this call; the toolbar
    // then falls back to a fixed position rather than disappearing.
    rect = null;
  }
  return { text, segmentId: segmentIdOf(source.anchorNode), rect };
}

/**
 * Ask a shadow root (or its document) for the current selection.
 *
 * Tried in order, because the exact API differs: `ShadowRoot.getSelection()` is
 * the one that reliably reports a selection made *inside* the shadow tree in
 * Gecko, and `document.getSelection()` can come back empty when the selection is
 * scoped to a shadow root.
 */
export function selectionOf(root: ShadowRoot | Document | null): SelectionLike | null {
  if (!root) {
    return null;
  }
  // `ShadowRoot.getSelection()` exists in Gecko and Blink but is not in the DOM
  // typings, so it is reached through a narrow cast.
  const scoped = (root as unknown as { getSelection?: () => SelectionLike | null }).getSelection?.();
  if (scoped) {
    return scoped;
  }
  const doc = (root as Document).getSelection ? (root as Document) : (root as ShadowRoot).ownerDocument;
  const fromDoc = doc?.getSelection?.();
  if (fromDoc) {
    return fromDoc as unknown as SelectionLike;
  }
  try {
    return (globalThis.getSelection?.() as unknown as SelectionLike) || null;
  } catch {
    return null;
  }
}

/**
 * The selection as it exists *inside* our shadow tree, or null.
 *
 * `document.getSelection()` reports the text of a shadow selection but retargets
 * its nodes to the host element: `anchorNode` is the outer div and
 * `getRangeAt(0)` describes the whole overlay, so the paragraph cannot be
 * identified and the toolbar has no position. `Selection.getComposedRanges()`
 * (Firefox 130+, reachable without types) returns the real nodes, which fixes
 * both. A selection that is not ours — the PDF's own text layer — is rejected,
 * so Zotero's popup and this toolbar cannot both open.
 */
export function shadowSelection(
  root: ShadowRoot | Document | null,
  owner: Node | null,
): SelectionHit | null {
  const selection = selectionOf(root) as
    | (SelectionLike & {
        getComposedRanges?: (options: { shadowRoots: ShadowRoot[] }) => unknown[];
      })
    | null;
  if (!selection) {
    return null;
  }
  let range: { startContainer?: Node; getBoundingClientRect?(): SelectionRect } | undefined;
  try {
    const composed =
      root instanceof Object && "host" in (root as ShadowRoot)
        ? selection.getComposedRanges?.({ shadowRoots: [root as ShadowRoot] })?.[0]
        : undefined;
    range =
      (composed as typeof range) ||
      (selection.getRangeAt?.(0) as unknown as typeof range) ||
      undefined;
  } catch {
    range = undefined;
  }
  const anchor = range?.startContainer ?? selection.anchorNode ?? null;
  if (anchor && owner && !inside(anchor, owner)) {
    // Someone else's selection (the PDF text layer).
    return null;
  }
  const source: SelectionLike = {
    isCollapsed: selection.isCollapsed,
    rangeCount: selection.rangeCount,
    toString: () => selection.toString(),
    anchorNode: anchor,
    getRangeAt: () => ({
      getBoundingClientRect: () =>
        range?.getBoundingClientRect
          ? range.getBoundingClientRect()
          : (undefined as unknown as SelectionRect),
    }),
  };
  return readSelectionFrom(source);
}

/** Is `node` inside our overlay? Answers for both real and retargeted nodes. */
function inside(node: Node, owner: Node): boolean {
  if (node === owner) {
    return true;
  }
  let current: any = node;
  let guard = 0;
  while (current && guard < 60) {
    guard += 1;
    if (current === owner) {
      return true;
    }
    current = current.parentNode || current.host || null;
  }
  return false;
}
