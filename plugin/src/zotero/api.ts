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

export function jumpToPage(reader: any, page: number): boolean {
  const index = Math.max(0, Math.floor(page) - 1);
  const attempts: (() => void)[] = [
    () => reader.navigate({ pageIndex: index }),
    () => reader._navigate({ pageIndex: index }),
    () => {
      const app = reader._iframeWindow?.PDFViewerApplication;
      if (app?.pdfViewer) {
        app.pdfViewer.currentPageNumber = index + 1;
      } else if (app) {
        app.page = index + 1;
      } else {
        throw new Error("no pdf viewer");
      }
    },
    () => {
      reader._internalReader?.navigate?.({ pageIndex: index });
    },
  ];
  for (const attempt of attempts) {
    try {
      attempt();
      return true;
    } catch {
      // Try the next strategy.
    }
  }
  return false;
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

export function isPdfReader(reader: any): boolean {
  try {
    const item = Zotero.Items.get(reader.itemID);
    return Boolean(item && item.isAttachment() && item.attachmentContentType === "application/pdf");
  } catch {
    return false;
  }
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
