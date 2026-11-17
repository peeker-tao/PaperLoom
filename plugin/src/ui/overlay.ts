import type { Segment } from "../types";
import type { RenderedPage } from "../zotero/api";

export interface OverlayBox {
  left: number;
  top: number;
  width: number;
  height: number;
  fontSize: number;
  lineHeight: number;
}

/** Minimum size (CSS px) for an overlay to hold readable text. */
export const MIN_OVERLAY_WIDTH = 16;
export const MIN_OVERLAY_HEIGHT = 6;

/**
 * Map a PDF-user-space bbox onto the rendered page bitmap.
 *
 * Segments store coordinates in PDF points with the origin at the bottom-left,
 * so the vertical axis is flipped. Rotated pages are skipped: pdf.js applies a
 * matrix that a plain scale + flip cannot reproduce, and a wrong overlay would
 * cover the wrong text.
 *
 * Returns null when the box is unusable (rotated page, bad bbox, or too small
 * to render a translation legibly).
 */
export function overlayGeometry(
  segment: Pick<Segment, "bbox">,
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
  // Scale the font to the original box height and let long translations clip
  // instead of spilling over neighbouring paragraphs.
  const fontSize = Math.max(5.5, Math.min(14, boxHeight * 0.62));
  return { left, top, width: boxWidth, height: boxHeight, fontSize, lineHeight: 1.16 };
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
