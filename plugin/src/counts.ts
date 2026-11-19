/**
 * The one definition of "how much of this paper is translated".
 *
 * Three screens used to answer that question with three different rules:
 *
 * - the footer divided by *every* segment (`105/472`), so a fully translated
 *   paper never reached the number it was comparing against;
 * - the partial-translation card dropped references, pictures and noise but
 *   kept formulas and table cells, which the server never translates;
 * - the reading toolbar dropped formulas and tables as well, giving a third
 *   denominator — and the bilingual header showed a fourth, per page.
 *
 * The mismatch was reported as "翻译段数有误": no single number was wrong on its
 * own, but they contradicted each other on one screen. The rule below mirrors
 * `paperloom_service.translate.is_translatable` on the server, so the client and
 * the job pipeline agree about what counts as pending work.
 */
import type { Segment } from "./types";

/** Kinds the translator is never asked for: citations, author blocks, layout
 * noise, display equations, table cells and the picture crops. */
export const SKIP_KINDS = new Set([
  "reference",
  "meta",
  "noise",
  "formula",
  "table",
  "figure",
]);

/** Fragments shorter than this carry no standalone meaning. */
export const MIN_TRANSLATE_CHARS = 12;

/** Letters only — a run of digits or punctuation is not prose. */
const LETTER = /\p{L}/u;

function hasProse(text: string): boolean {
  if (!text) {
    return false;
  }
  let letters = 0;
  for (const char of text) {
    if (LETTER.test(char)) {
      letters += 1;
    }
  }
  const total = [...text].length;
  return letters >= 4 && letters / Math.max(1, total) >= 0.35;
}

/**
 * Would the server send this segment to the translator?
 *
 * A heading is prose the reader needs ("3 Method", "5 Related Work"); the length
 * floor exists to drop fragments, and headings are not fragments.
 */
export function isTranslatable(segment: Segment): boolean {
  if (SKIP_KINDS.has(segment.kind)) {
    return false;
  }
  const text = (segment.text || "").trim();
  if (segment.kind === "title" || segment.kind === "heading") {
    return hasProse(text);
  }
  return text.length >= MIN_TRANSLATE_CHARS && hasProse(text);
}

export interface TranslationCounts {
  /** Segments the translator will be asked for. */
  total: number;
  /** Of those, the ones that already have a translation. */
  done: number;
  /** Segments that exist but are never translated (pictures, citations, ...). */
  skipped: number;
}

function count(segments: Segment[]): TranslationCounts {
  let total = 0;
  let done = 0;
  for (const segment of segments) {
    if (!isTranslatable(segment)) {
      continue;
    }
    total += 1;
    if (segment.translation) {
      done += 1;
    }
  }
  return { total, done, skipped: segments.length - total };
}

/** Counts for a set of segments — the whole paper, or one page. */
export function translationCounts(segments: Segment[]): TranslationCounts {
  return count(segments);
}

/** "105/112" — never "105/472". */
export function describeCounts(counts: TranslationCounts): string {
  return `${counts.done}/${counts.total}`;
}
