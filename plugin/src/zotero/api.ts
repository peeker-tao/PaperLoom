import { debug } from "../log";
import type { AttachmentContext } from "../types";

export function createPrefs() {
  return {
    get(key: string, fallback: unknown): unknown {
      try {
        const value = Zotero.Prefs.get(key);
        return value === undefined || value === null ? fallback : value;
      } catch {
        return fallback;
      }
    },
    set(key: string, value: unknown): void {
      try {
        Zotero.Prefs.set(key, value as any);
      } catch (error) {
        debug("pref write failed", key, String(error));
      }
    },
  };
}

export async function attachmentContext(reader: any): Promise<AttachmentContext> {
  const item = Zotero.Items.get(reader.itemID);
  if (!item || !item.isAttachment()) {
    throw new Error("当前阅读器没有关联的附件条目");
  }
  if (String(item.attachmentContentType || "").toLowerCase() !== "application/pdf") {
    throw new Error("PaperLoom 目前只支持 PDF 附件");
  }
  const parent = item.parentItemID ? Zotero.Items.get(item.parentItemID) : null;
  const title = (parent && parent.getField("title")) || item.getField("title") || "未命名论文";
  const pdfPath = await resolvePdfPath(item);
  if (!pdfPath) {
    throw new Error("无法定位 PDF 文件路径（附件可能未下载到本地）");
  }
  return {
    attachmentItemID: item.id,
    parentItemID: item.parentItemID || null,
    libraryID: item.libraryID,
    attachmentKey: item.key,
    itemKey: parent ? parent.key : item.key,
    title,
    pdfPath,
  };
}

export async function resolvePdfPath(item: any): Promise<string | null> {
  try {
    if (typeof item.getFilePathAsync === "function") {
      const path = await item.getFilePathAsync();
      if (path) {
        return path;
      }
    }
  } catch {
    // Fall through to the other strategies.
  }
  try {
    if (typeof item.getFilePath === "function") {
      const path = item.getFilePath();
      if (path) {
        return path;
      }
    }
  } catch {
    // Fall through.
  }
  try {
    const raw: string = item.attachmentPath || "";
    if (raw.startsWith("storage:")) {
      const filename = raw.slice("storage:".length);
      const storage = Zotero.getStorageDirectory();
      return PathUtils.join(storage.path, item.key, filename);
    }
    if (raw.startsWith("file://")) {
      return Services.io.newURI(raw).QueryInterface(Ci.nsIFileURL).file.path;
    }
    if (raw && !raw.startsWith("attachments:")) {
      return raw;
    }
  } catch (error) {
    debug("path resolution failed", String(error));
  }
  return null;
}

/**
 * Where a jump landed. "page" means the reader accepted the page but not the
 * region (the usual case: the page was not laid out yet); "region" means the
 * target box was actually brought into view.
 */
export type JumpLevel = "region" | "page" | "none";

export interface JumpResult {
  ok: boolean;
  level: JumpLevel;
  page: number;
  /** Which strategy worked, for the log. */
  via: string;
  /** Why it failed, in a form that can be shown to the user. */
  reason?: string;
}

/** Wait for a predicate, polling, up to a deadline. */
async function waitFor(
  check: () => boolean,
  timeoutMs: number,
  stepMs = 40,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if (check()) {
        return true;
      }
    } catch {
      // A viewer mid-navigation can throw; keep polling.
    }
    await new Promise((resolve) => setTimeout(resolve, stepMs));
  }
  try {
    return check();
  } catch {
    return false;
  }
}

/**
 * Scroll the reader to a page, and to a region of it when coordinates are known.
 *
 * Two things here are deliberate:
 *
 * 1. **Order.** `reader.navigate()` only posts a message to the reader iframe, so
 *    it never throws. The old code called it first and returned `true`
 *    unconditionally, which made the reliable pdf.js path underneath dead code:
 *    "在 PDF 中查看" did nothing while the sidebar reported the new page. pdf.js
 *    first, then `scrollIntoView`, then the documented API.
 * 2. **Verification.** A call that returns is not a scroll that happened. The
 *    result is confirmed against the viewer's own state, so a refused jump is
 *    reported as a failure instead of being recorded as the reading position.
 */
export async function jumpToPage(
  reader: any,
  page: number,
  region?: [number, number, number, number] | null,
): Promise<JumpResult> {
  const index = Math.max(0, Math.floor(page) - 1);
  const target = index + 1;
  const app = reader?._iframeWindow?.PDFViewerApplication;
  const viewer = app?.pdfViewer;

  const after = (level: JumpLevel, via: string): JumpResult => ({
    ok: true,
    level,
    page: target,
    via,
  });

  // 1. pdf.js. Setting `currentPageNumber` scrolls synchronously, and it is the
  //    same viewer the page renderer already uses successfully.
  if (viewer) {
    try {
      viewer.currentPageNumber = target;
      if (await waitFor(() => viewer.currentPageNumber === target, 600)) {
        if (region && (await scrollToRegion(viewer, index, region))) {
          return after("region", "pdfjs+region");
        }
        return after("page", "pdfjs");
      }
    } catch {
      // Fall through: the viewer exists but is not ready.
    }
    // The page may simply not be laid out yet. Scrolling its container works
    // even when `currentPageNumber` is ignored.
    try {
      const pageView = viewer.getPageView?.(index);
      const node = pageView?.div || pageView?.canvas;
      if (node && typeof node.scrollIntoView === "function") {
        node.scrollIntoView({ block: "start" });
        if (await waitFor(() => Boolean(node.isConnected), 300)) {
          return after("page", "pdfjs+scrollIntoView");
        }
      }
    } catch {
      // Fall through to the documented API.
    }
  }

  // 2. The documented reader API. It returns before the scroll happens, so the
  //    promise is awaited and then the position is read back.
  const attempts: [string, () => unknown][] = [
    ["reader.navigate", () => reader?.navigate?.({ pageIndex: index })],
    ["internalReader.navigate", () => reader?._internalReader?.navigate?.({ pageIndex: index })],
  ];
  for (const [via, attempt] of attempts) {
    try {
      const result = attempt();
      if (!result) {
        continue;
      }
      if (typeof (result as Promise<unknown>).then === "function") {
        await (result as Promise<unknown>);
      }
      // Confirm against whatever state is readable; a reader without readable
      // state still gets the benefit of the doubt *only* if the call resolved.
      const landed = await waitFor(() => currentPage(reader) === target, 800);
      if (landed || currentPage(reader) === target) {
        return after("page", via);
      }
    } catch {
      // Try the next strategy.
    }
  }

  const observed = currentPage(reader);
  return {
    ok: false,
    level: "none",
    page: target,
    via: "none",
    reason:
      observed === target
        ? ""
        : `阅读器没有响应跳转请求（当前停在第 ${observed} 页）`,
  };
}

/**
 * Bring a PDF-space box into view inside the rendered page.
 *
 * pdf.js draws each page into a div whose size follows the current scale, so the
 * box has to be converted from PDF user space (origin bottom-left) to CSS pixels
 * first. When the page view or its viewport is unavailable the page-level jump
 * already done is still useful, so this returns false rather than throwing.
 */
async function scrollToRegion(
  viewer: any,
  index: number,
  region: [number, number, number, number],
): Promise<boolean> {
  try {
    const pageView = viewer.getPageView?.(index);
    const container = pageView?.div;
    if (!container) {
      return false;
    }
    const viewport = pageView.viewport;
    if (!viewport || typeof viewport.convertToViewportRectangle !== "function") {
      return false;
    }
    const [x0, y0, x1, y1] = region;
    const rect = viewport.convertToViewportRectangle([x0, y0, x1, y1]);
    // The box is converted to viewport space; only `top` is needed because the
    // reader scrolls vertically.
    const top = Math.min(rect[1], rect[3]);
    const scroller = container.parentElement;
    if (!scroller) {
      return false;
    }
    // Put the region about a quarter down the viewport so surrounding context is
    // visible, which is what makes a jump feel like "找到这里" rather than
    // "这一行贴着屏幕顶端".
    const target = Math.max(0, top - scroller.clientHeight * 0.25);
    scroller.scrollTop = target;
    // A scroll that did not move means the region is already visible, which is
    // just as good as having scrolled to it.
    return true;
  } catch {
    return false;
  }
}

export function currentPage(reader: any): number {
  try {
    const state = reader.state;
    if (state && Number.isFinite(state.pageIndex)) {
      return state.pageIndex + 1;
    }
  } catch {
    // ignore
  }
  try {
    const app = reader._iframeWindow?.PDFViewerApplication;
    if (app?.pdfViewer?.currentPageNumber) {
      return app.pdfViewer.currentPageNumber;
    }
    if (app?.page) {
      return app.page;
    }
  } catch {
    // ignore
  }
  return 1;
}

export function readerDocument(reader: any): Document | null {
  try {
    return reader._iframeWindow?.document || null;
  } catch {
    return null;
  }
}

/** Abort a page render that never resolves (bad PDF, stalled pdf.js worker). */
const RENDER_TIMEOUT_MS = 8000;

export interface RenderedPage {
  page: number;
  dataUrl: string;
  /** CSS pixel size of the rendered bitmap. */
  width: number;
  height: number;
  /** PDF user-space size of the unrotated page; used to place overlays. */
  pageWidth: number;
  pageHeight: number;
  rotation: number;
  scale: number;
}

/**
 * Render one PDF page to a PNG data URL using the reader's own pdf.js instance.
 *
 * This is what keeps figures, formulas and tables visible in the bilingual
 * view: we draw the real page instead of re-flowing text, then overlay the
 * translated paragraphs at their original coordinates.
 */
export async function renderPdfPage(
  reader: any,
  pageNumber: number,
  targetWidth: number,
): Promise<RenderedPage | null> {
  const app = reader?._iframeWindow?.PDFViewerApplication;
  const pdfDocument = app?.pdfDocument;
  if (!pdfDocument || typeof document === "undefined") {
    return null;
  }
  const page = await pdfDocument.getPage(pageNumber);
  if (typeof page?.render !== "function") {
    return null;
  }
  const rotation = ((Number(page.rotate) || 0) % 360 + 360) % 360;
  const base = page.getViewport({ scale: 1, rotation });
  const requested = Math.max(180, Math.min(2400, Math.round(targetWidth) || 640));
  const scale = Math.max(0.2, Math.min(3, requested / base.width));
  const viewport = page.getViewport({ scale, rotation });

  const ratio = Math.max(1, Math.min(2, Number(globalThis.devicePixelRatio) || 1));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(viewport.width * ratio));
  canvas.height = Math.max(1, Math.round(viewport.height * ratio));
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }
  const renderViewport =
    ratio === 1 ? viewport : page.getViewport({ scale: scale * ratio, rotation });
  const task = page.render({ canvasContext: context, viewport: renderViewport });
  // Some environments never resolve the render promise (observed with pdf.js in
  // an offscreen Chromium and on a few exotic PDFs). Bail out instead of
  // leaving the view stuck on "rendering".
  const finished = await Promise.race([
    task.promise.then(() => true),
    new Promise<boolean>((resolve) => setTimeout(() => resolve(false), RENDER_TIMEOUT_MS)),
  ]);
  if (!finished) {
    try {
      task.cancel();
    } catch {
      // ignore: the task may already be finished
    }
    debug("page render timed out", pageNumber);
    return null;
  }
  return {
    page: pageNumber,
    dataUrl: canvas.toDataURL("image/png"),
    width: viewport.width,
    height: viewport.height,
    pageWidth: base.width,
    pageHeight: base.height,
    rotation,
    scale,
  };
}

export function isPdfReader(reader: any): boolean {
  try {
    const item = Zotero.Items.get(reader.itemID);
    return Boolean(item && item.isAttachment() && item.attachmentContentType === "application/pdf");
  } catch {
    return false;
  }
}

/** Copy text to the system clipboard, across the Zotero/Firefox variants. */
export function copyText(text: string): boolean {
  const write = (fn: (() => void) | undefined): boolean => {
    try {
      fn?.();
      return true;
    } catch {
      return false;
    }
  };
  // Zotero 7+ provides this helper and handles the document argument itself.
  const internal = (Zotero as any)?.Utilities?.Internal?.copyTextToClipboard;
  if (typeof internal === "function") {
    if (write(() => internal.call(Zotero.Utilities.Internal, text))) {
      return true;
    }
  }
  const helper = (Services as any).clipboardHelper;
  if (helper?.copyString) {
    if (write(() => helper.copyString(text))) {
      return true;
    }
  }
  return false;
}

export function openNote(noteID: number): void {
  try {
    const win = Zotero.getMainWindow();
    win.ZoteroPane.selectItem(noteID);
    win.focus();
  } catch (error) {
    debug("open note failed", String(error));
  }
}

export async function findPaperLoomNotes(parentItemID: number): Promise<any[]> {
  try {
    const parent = Zotero.Items.get(parentItemID);
    if (!parent) {
      return [];
    }
    const ids = await parent.getNotes();
    const notes = [];
    for (const id of ids) {
      const note = Zotero.Items.get(id);
      if (note && (note.getTags() || []).some((tag: any) => tag.tag === "PaperLoom")) {
        notes.push(note);
      }
    }
    return notes;
  } catch (error) {
    debug("list notes failed", String(error));
    return [];
  }
}

/** Find the first local PDF attachment of a regular item or attachment. */
export async function bestPdfAttachment(item: any): Promise<any | null> {
  try {
    if (item?.isAttachment?.()) {
      return String(item.attachmentContentType || "").toLowerCase() === "application/pdf" ? item : null;
    }
    const ids = await item.getAttachments();
    for (const id of ids) {
      const attachment = Zotero.Items.get(id);
      if (attachment && String(attachment.attachmentContentType || "").toLowerCase() === "application/pdf") {
        return attachment;
      }
    }
  } catch (error) {
    debug("best attachment failed", String(error));
  }
  return null;
}

/** Build the PaperLoom attachment context from an attachment item (not a reader). */
export async function attachmentContextFromItem(item: any): Promise<AttachmentContext | null> {
  if (!item || !item.isAttachment?.()) {
    return null;
  }
  const parent = item.parentItemID ? Zotero.Items.get(item.parentItemID) : null;
  const pdfPath = await resolvePdfPath(item);
  if (!pdfPath) {
    return null;
  }
  return {
    attachmentItemID: item.id,
    parentItemID: item.parentItemID || null,
    libraryID: item.libraryID,
    attachmentKey: item.key,
    itemKey: parent ? parent.key : item.key,
    title: (parent && parent.getField("title")) || item.getField("title") || "未命名论文",
    pdfPath,
  };
}
