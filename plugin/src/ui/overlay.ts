import type { Segment } from "../types";
import type { RenderedPage } from "../zotero/api";

export interface OverlayBox {
  left: number;
  top: number;
  width: number;
  height: number;
  fontSize: number;
  lineHeight: number;
  /** Pre-wrapped lines; the plugin must not rely on CSS wrapping. */
  lines: string[];
}

/** Minimum size (CSS px) for an overlay to hold readable text. */
export const MIN_OVERLAY_WIDTH = 16;
export const MIN_OVERLAY_HEIGHT = 6;
export const MIN_FONT = 5;
export const MAX_FONT = 20;
export const LINE_HEIGHT = 1.16;

// Glyph advances as a fraction of the font size. Estimating instead of
// measuring keeps the layout identical here and in the Python preview
// (scripts/overlay_layout.py) and avoids a canvas measurement per paragraph.
const CJK_WIDTH = 1;
const LATIN_WIDTH = 0.55;
const SPACE_WIDTH = 0.3;
const NARROW = "iljI.,:;'|!()[]{}/";
const WIDE = "mwMW@%";
const PUNCT_CJK = "（）【】《》“”‘’，。、；：！？·—…";
/** Characters that must never start a line (CJK typesetting rule). */
const NO_LINE_START = "，。、；：！？）》”』】·…％‰℃";

export function charWidth(char: string): number {
  if (char === " ") {
    return SPACE_WIDTH;
  }
  if (PUNCT_CJK.includes(char) || /[\u4e00-\u9fff\u3000-\u303f]/.test(char)) {
    return CJK_WIDTH;
  }
  if (NARROW.includes(char)) {
    return LATIN_WIDTH * 0.55;
  }
  if (WIDE.includes(char)) {
    return LATIN_WIDTH * 1.45;
  }
  return LATIN_WIDTH;
}

function isLatin(char: string): boolean {
  return /[A-Za-z0-9\-_+./%()[\]]/.test(char);
}

/** Keep closing punctuation off the start of a line. */
function applyKinsoku(lines: string[]): string[] {
  for (let index = 1; index < lines.length; index += 1) {
    while (lines[index] && NO_LINE_START.includes(lines[index][0])) {
      lines[index - 1] += lines[index][0];
      lines[index] = lines[index].slice(1);
    }
  }
  return lines.filter((line) => line.length > 0);
}

/** Greedy wrap: never split a Latin word, always allow a CJK break. */
export function wrapEstimated(text: string, fontSize: number, width: number): string[] {
  const limit = width;
  const lines: string[] = [];
  let current = "";
  let currentWidth = 0;
  let index = 0;
  const flush = () => {
    if (current) {
      lines.push(current.trimEnd());
    }
    current = "";
    currentWidth = 0;
  };

  while (index < text.length) {
    const char = text[index];
    if (char === "\n") {
      flush();
      index += 1;
      continue;
    }
    if (isLatin(char)) {
      let end = index;
      while (end < text.length && isLatin(text[end])) {
        end += 1;
      }
      const word = text.slice(index, end);
      let wordWidth = 0;
      for (const piece of word) {
        wordWidth += charWidth(piece) * fontSize;
      }
      if (currentWidth + wordWidth > limit && current) {
        flush();
      }
      if (wordWidth > limit && !current) {
        for (const piece of word) {
          const advance = charWidth(piece) * fontSize;
          if (currentWidth + advance > limit && current) {
            flush();
          }
          current += piece;
          currentWidth += advance;
        }
        index = end;
        continue;
      }
      current += word;
      currentWidth += wordWidth;
      index = end;
      continue;
    }
    const advance = charWidth(char) * fontSize;
    if (currentWidth + advance > limit && current) {
      flush();
    }
    current += char;
    currentWidth += advance;
    index += 1;
  }
  flush();
  return applyKinsoku(lines);
}

function fits(lines: string[], fontSize: number, height: number, width: number): boolean {
  if (!lines.length) {
    return true;
  }
  if (lines.length * fontSize * LINE_HEIGHT > height + 0.5) {
    return false;
  }
  let widest = 0;
  for (const line of lines) {
    let lineWidth = 0;
    for (const char of line) {
      lineWidth += charWidth(char) * fontSize;
    }
    widest = Math.max(widest, lineWidth);
  }
  return widest <= width + 1.5;
}

/**
 * Largest font size at which the whole translation fits inside the box.
 *
 * Returns null when even the minimum size does not fit: a truncated sentence is
 * worse than a visible gap, because the reader cannot tell that text is missing.
 */
export function fitFontSize(text: string, width: number, height: number): number | null {
  if (width < 12 || height < 5 || !text.trim()) {
    return null;
  }
  const preferred = Math.max(MIN_FONT, Math.min(MAX_FONT, height * 0.9));
  let size = Math.round(preferred * 2) / 2;
  while (size >= MIN_FONT) {
    const lines = wrapEstimated(text, size, width - 2);
    if (fits(lines, size, height - 1, width - 2)) {
      return Math.round(size * 10) / 10;
    }
    size -= 0.5;
  }
  return null;
}

/**
 * Map a PDF-user-space bbox onto the rendered page bitmap and lay out the
 * translation inside it.
 *
 * Segments store coordinates in PDF points with the origin at the bottom-left,
 * so the vertical axis is flipped. Rotated pages are skipped: pdf.js applies a
 * matrix that a plain scale + flip cannot reproduce, and a wrong overlay would
 * cover the wrong text. Boxes covering most of the page are rejected too: they
 * come from a segmentation accident and would paint over figures and every
 * other paragraph.
 */
export function overlayGeometry(
  segment: Pick<Segment, "bbox" | "translation">,
  image: Pick<RenderedPage, "width" | "height" | "pageWidth" | "pageHeight" | "rotation">,
): OverlayBox | null {
  if (!image.pageWidth || !image.pageHeight || !image.width) {
    return null;
  }
  if (((Number(image.rotation) || 0) % 360 + 360) % 360 !== 0) {
    return null;
  }
  const bbox = segment.bbox;
  if (!Array.isArray(bbox) || bbox.length < 4) {
    return null;
  }
  const [x0, y0, x1, y1] = bbox.map((value) => Number(value) || 0);
  if (!(x1 > x0) || !(y1 > y0)) {
    return null;
  }
  // A single paragraph never spans most of a page; such a box comes from a
  // segmentation accident and would paint over figures and other paragraphs.
  if (y1 - y0 > image.pageHeight * 0.7 || x1 - x0 > image.pageWidth * 0.96) {
    return null;
  }
  const ratio = image.width / image.pageWidth;
  const boxWidth = (x1 - x0) * ratio;
  const boxHeight = (y1 - y0) * ratio;
  if (boxWidth < MIN_OVERLAY_WIDTH || boxHeight < MIN_OVERLAY_HEIGHT) {
    return null;
  }
  const left = x0 * ratio;
  const top = (image.pageHeight - y1) * ratio;
  // Keep the box inside the bitmap even when the PDF media box is offset.
  if (left < -1 || top < -1) {
    return null;
  }
  const translation = (segment.translation || "").trim();
  const fontSize = fitFontSize(translation, boxWidth, boxHeight);
  if (fontSize === null) {
    return null;
  }
  const lines = wrapEstimated(
    translation,
    Math.max(MIN_FONT, Math.round(fontSize)),
    boxWidth - 2,
  );
  return {
    left,
    top,
    width: boxWidth,
    height: boxHeight,
    fontSize,
    lineHeight: LINE_HEIGHT,
    lines,
  };
}

/** Rendered-pixel size of a page at a given column width (keeps aspect ratio). */
export function fitPage(
  image: Pick<RenderedPage, "width" | "height" | "pageWidth" | "pageHeight">,
  columnWidth: number,
): { width: number; height: number } {
  if (!image.pageWidth || !image.pageHeight) {
    return { width: image.width, height: image.height };
  }
  const width = Math.max(40, columnWidth);
  return { width, height: (image.pageHeight / image.pageWidth) * width };
}
