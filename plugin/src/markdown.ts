/**
 * Minimal Markdown renderer for AI output. Everything is HTML-escaped before
 * applying a small, intentional subset. Citation markers become either
 * clickable spans (UI) or zotero:// links (notes).
 */

export interface CitationTarget {
  page?: number;
  href?: string;
}

export interface RenderOptions {
  resolve?: (segmentId: string) => CitationTarget | null;
  citationsAsLinks?: boolean;
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inline(text: string, options: RenderOptions): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, (_m, code: string) => `<code>${code}</code>`);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  out = out.replace(/\[\[(?:seg|SEG):([A-Za-z0-9_\-:]+)\]\]/g, (_match, segmentId: string) => {
    const target = options.resolve?.(segmentId) || null;
    const label = target?.page ? `p.${target.page}` : "引用";
    if (options.citationsAsLinks && target?.href) {
      return `<a href="${escapeHtml(target.href)}" data-cite="${escapeHtml(segmentId)}">${label}</a>`;
    }
    return `<button type="button" class="pl-cite" data-cite="${escapeHtml(segmentId)}" title="跳回原文">${label}</button>`;
  });
  return out;
}

export function renderMarkdown(markdown: string, options: RenderOptions = {}): string {
  const lines = (markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let inCode = false;
  let inTable = false;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };
  const closeTable = () => {
    if (inTable) {
      html.push("</table>");
      inTable = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (line.startsWith("```")) {
      closeList();
      closeTable();
      if (inCode) {
        html.push("</code></pre>");
      } else {
        html.push('<pre><code>');
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      html.push(escapeHtml(rawLine) + "\n");
      continue;
    }
    if (!line.trim()) {
      closeList();
      closeTable();
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      closeList();
      closeTable();
      const level = heading[1].length + 2;
      html.push(`<h${level}>${inline(heading[2], options)}</h${level}>`);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      closeTable();
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${inline(line.replace(/^[-*]\s+/, ""), options)}</li>`);
      continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      closeTable();
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${inline(line.replace(/^\d+[.)]\s+/, ""), options)}</li>`);
      continue;
    }
    if (line.startsWith("> ")) {
      closeList();
      closeTable();
      html.push(`<blockquote>${inline(line.slice(2), options)}</blockquote>`);
      continue;
    }
    if (/^\|.*\|$/.test(line)) {
      closeList();
      if (!inTable) {
        html.push('<table class="pl-table">');
        inTable = true;
      }
      const cells = line
        .slice(1, -1)
        .split("|")
        .map((cell) => cell.trim());
      if (cells.every((cell) => /^:?-{2,}:?$/.test(cell))) {
        continue;
      }
      html.push(`<tr>${cells.map((cell) => `<td>${inline(cell, options)}</td>`).join("")}</tr>`);
      continue;
    }
    if (/^-{3,}$/.test(line)) {
      closeList();
      closeTable();
      html.push("<hr/>");
      continue;
    }
    closeList();
    closeTable();
    html.push(`<p>${inline(line, options)}</p>`);
  }
  closeList();
  closeTable();
  if (inCode) {
    html.push("</code></pre>");
  }
  return html.join("\n");
}

export function streamableText(markdown: string): string {
  return markdown.replace(/\[\[(?:seg|SEG):[^\]]+\]\]/g, "").trimEnd();
}
