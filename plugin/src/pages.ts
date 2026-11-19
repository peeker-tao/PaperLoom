/**
 * Page-range parsing for "指定页" translation.
 *
 * Kept as a pure function so the dialog's validation can be tested without
 * spawning Zotero: getting this wrong means translating the wrong pages, which
 * costs real tokens and is annoying to notice.
 */

export interface ParseResult {
  /** Sorted, de-duplicated pages. Empty when the input was blank ("whole paper"). */
  pages: number[];
  /** Null when the input is unusable; the message is shown next to the field. */
  error: string | null;
}

/**
 * Parse "1-3,5" (also accepts full-width commas, spaces and ~ as a range dash).
 *
 * A blank input is not an error: the caller treats it as "the whole paper",
 * which is what pressing Enter on an empty dialog should do.
 */
export function parsePageInput(input: string): ParseResult {
  const text = String(input || "").trim();
  if (!text) {
    return { pages: [], error: null };
  }
  const pages = new Set<number>();
  // Split on commas (half and full width) and whitespace.
  for (const part of text.split(/[,，、\s]+/).filter(Boolean)) {
    const match = /^(\d+)(?:\s*[-~－—]\s*(\d+))?$/.exec(part);
    if (!match) {
      return { pages: [], error: `无法识别的页码片段「${part}」，请输入如 1-3,5` };
    }
    const start = Number(match[1]);
    const end = match[2] ? Number(match[2]) : start;
    if (start < 1) {
      return { pages: [], error: "页码从 1 开始" };
    }
    if (end < start) {
      return { pages: [], error: `范围「${part}」的结束页小于起始页` };
    }
    if (end > 5000) {
      return { pages: [], error: `页码 ${end} 过大，请检查是否填错` };
    }
    for (let page = start; page <= end; page += 1) {
      pages.add(page);
    }
  }
  return { pages: Array.from(pages).sort((a, b) => a - b), error: null };
}

/**
 * Format pages back into the compact input form, e.g. "1-3,5".
 *
 * Used by the page grid: clicking tiles has to update the text field, and
 * pasting a computed list of 200 numbers into it would be unreadable.
 */
export function formatPageInput(pages: number[]): string {
  const sorted = Array.from(new Set(pages.filter((page) => page >= 1))).sort((a, b) => a - b);
  if (!sorted.length) {
    return "";
  }
  const runs: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];
  for (const page of sorted.slice(1)) {
    if (page === previous + 1) {
      previous = page;
      continue;
    }
    runs.push(start === previous ? String(start) : `${start}-${previous}`);
    start = page;
    previous = page;
  }
  runs.push(start === previous ? String(start) : `${start}-${previous}`);
  return runs.join(",");
}

/**
 * Turn a parsed range into a human summary, e.g. "1-3, 5（共 4 页）".
 *
 * Consecutive pages are collapsed so a 200-page selection does not produce a
 * 200-number list in the dialog.
 */
export function describePages(pages: number[]): string {
  if (!pages.length) {
    return "全文";
  }
  const runs: string[] = [];
  let start = pages[0];
  let previous = pages[0];
  for (const page of pages.slice(1)) {
    if (page === previous + 1) {
      previous = page;
      continue;
    }
    runs.push(start === previous ? String(start) : `${start}-${previous}`);
    start = page;
    previous = page;
  }
  runs.push(start === previous ? String(start) : `${start}-${previous}`);
  return `${runs.join(", ")}（共 ${pages.length} 页）`;
}
