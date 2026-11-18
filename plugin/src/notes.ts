import type { AttachmentContext, Citation, Segment, Selection } from "./types";
import { escapeHtml, renderMarkdown } from "./markdown";

export interface NoteInput {
  dedupeKey: string;
  docTitle: string;
  attachment: AttachmentContext;
  page?: number;
  selection?: Selection | null;
  translation?: string;
  question?: string;
  answer?: string;
  citations?: Citation[];
  segments?: Segment[];
  model?: string;
  kind?: string;
}

function pageLink(attachmentKey: string, page?: number): string {
  const suffix = page ? `?page=${page}` : "";
  return `zotero://open-pdf/library/items/${attachmentKey}${suffix}`;
}

export function buildNoteHtml(input: NoteInput): string {
  const { attachment, page, selection, translation, question, answer, citations, segments } = input;
  const pages = page || selection?.page;
  const parts: string[] = [];
  parts.push(`<div data-paperloom-key="${escapeHtml(input.dedupeKey)}">`);
  parts.push(`<h2>PaperLoom · ${escapeHtml(selection ? "选区笔记" : "阅读笔记")}</h2>`);
  parts.push(`<p><strong>论文：</strong>${escapeHtml(input.docTitle)}</p>`);
  if (pages) {
    parts.push(
      `<p><strong>位置：</strong><a href="${escapeHtml(pageLink(attachment.attachmentKey, pages))}">第 ${pages} 页</a></p>`,
    );
  }
  if (selection?.text) {
    parts.push(`<blockquote>${escapeHtml(selection.text)}</blockquote>`);
  }
  if (translation) {
    parts.push(`<p><strong>译文：</strong>${escapeHtml(translation)}</p>`);
  }
  if (question) {
    parts.push(`<p><strong>问题：</strong>${escapeHtml(question)}</p>`);
  }
  if (answer) {
    const html = renderMarkdown(answer, {
      citationsAsLinks: true,
      resolve: (segmentId) => {
        const segment = segments?.find((item) => item.id === segmentId);
        if (!segment) {
          return null;
        }
        return {
          page: segment.page,
          href: pageLink(attachment.attachmentKey, segment.page),
        };
      },
    });
    parts.push(`<div class="paperloom-answer">${html}</div>`);
  }
  if (citations?.length) {
    parts.push("<h3>原文依据</h3>");
    for (const citation of citations) {
      parts.push(
        `<p>· <a href="${escapeHtml(pageLink(attachment.attachmentKey, citation.page))}">第 ${citation.page} 页</a>` +
          `：${escapeHtml(citation.quote)}</p>`,
      );
    }
  }
  if (input.kind) {
    parts.push(`<p><strong>分析类型：</strong>${escapeHtml(input.kind)}</p>`);
  }
  parts.push(
    `<p><em>模型：${escapeHtml(input.model || "未知")} · 保存时间：${new Date().toLocaleString("zh-CN")}</em></p>`,
  );
  parts.push("</div>");
  return parts.join("\n");
}

export async function saveNote(
  input: NoteInput,
  parentItemID: number,
  libraryID: number,
  noteIndex: { get(): Record<string, string>; set(value: Record<string, string>): void },
): Promise<{ note: any; updated: boolean }> {
  const html = buildNoteHtml(input);
  const index = noteIndex.get();
  const existingKey = index[input.dedupeKey];
  if (existingKey) {
    try {
      const existing = Zotero.Items.getByLibraryAndKey(libraryID, existingKey);
      if (existing) {
        existing.setNote(html);
        await existing.saveTx();
        return { note: existing, updated: true };
      }
    } catch {
      // Fall through and create a new note.
    }
  }
  const note = new Zotero.Item("note");
  note.libraryID = libraryID;
  note.parentID = parentItemID;
  note.setNote(html);
  note.addTag("PaperLoom", 1);
  await note.saveTx();
  index[input.dedupeKey] = note.key;
  noteIndex.set(index);
  return { note, updated: false };
}

/**
 * Save the whole bilingual document (Markdown, English then Chinese) as a note.
 *
 * Re-saving overwrites the same note instead of piling up copies, which is what
 * a reader expects after re-translating a paper.
 */
export async function saveMarkdownNote(
  input: { dedupeKey: string; docTitle: string; attachment: AttachmentContext; markdown: string; model?: string },
  parentItemID: number,
  libraryID: number,
  noteIndex: { get(): Record<string, string>; set(value: Record<string, string>): void },
): Promise<{ note: any; updated: boolean }> {
  const body = renderMarkdown(input.markdown);
  const html = [
    `<div data-paperloom-key="${escapeHtml(input.dedupeKey)}">`,
    `<h2>PaperLoom · 全文双语（英中对照）</h2>`,
    `<p><strong>论文：</strong>${escapeHtml(input.docTitle)}</p>`,
    `<p><a href="zotero://open-pdf/library/items/${escapeHtml(input.attachment.attachmentKey)}">在 PDF 中打开</a>` +
      ` · 生成模型：${escapeHtml(input.model || "未知")} · ${new Date().toLocaleString("zh-CN")}</p>`,
    `<div class="paperloom-markdown">${body}</div>`,
    "</div>",
  ].join("\n");

  const index = noteIndex.get();
  const existingKey = index[input.dedupeKey];
  if (existingKey) {
    try {
      const existing = Zotero.Items.getByLibraryAndKey(libraryID, existingKey);
      if (existing) {
        existing.setNote(html);
        await existing.saveTx();
        return { note: existing, updated: true };
      }
    } catch {
      // Fall through and create a new note.
    }
  }
  const note = new Zotero.Item("note");
  note.libraryID = libraryID;
  note.parentID = parentItemID;
  note.setNote(html);
  note.addTag("PaperLoom", 1);
  await note.saveTx();
  index[input.dedupeKey] = note.key;
  noteIndex.set(index);
  return { note, updated: false };
}

export function noteIndexPref(prefs: { get(key: string, fallback: unknown): unknown; set(key: string, value: unknown): void }) {
  return {
    get(): Record<string, string> {
      try {
        return JSON.parse(String(prefs.get("extensions.paperloom.noteIndex", "{}"))) || {};
      } catch {
        return {};
      }
    },
    set(value: Record<string, string>): void {
      const entries = Object.entries(value);
      // Keep the index bounded; old entries simply create new notes again.
      const trimmed = Object.fromEntries(entries.slice(-500));
      prefs.set("extensions.paperloom.noteIndex", JSON.stringify(trimmed));
    },
  };
}
