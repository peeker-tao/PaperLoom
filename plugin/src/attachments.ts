/**
 * Composer image attachments: what may be sent, and what to say when it may not.
 *
 * All of this is pure so it can be tested without a DOM. The browser-facing parts
 * (file reading, paste handling) live in `ChatPanel`, but the *decisions* — which
 * format, how large, how many — belong here, because a rule that lives in a React
 * component is a rule that silently drifts.
 *
 * The cap on the number of images is not arbitrary: the provider charges per
 * image and starts dropping detail beyond a few, so four is enough for a
 * before/after comparison and small enough to stay honest about cost.
 */

export interface ChatImage {
  id: string;
  /** `data:image/...;base64,...` — the only form the service accepts. */
  dataUrl: string;
  caption: string;
  name: string;
}

export interface ImageCandidate {
  type: string;
  /** Bytes. */
  size: number;
  name?: string;
}

export const MAX_IMAGES = 4;
/** Per image, in bytes. A 1400px-wide figure crop lands around 300KB. */
export const MAX_IMAGE_BYTES = 2_500_000;
export const MAX_TOTAL_BYTES = 6_000_000;

export const ACCEPTED_MIMES = ["image/png", "image/jpeg", "image/webp"];
export const ACCEPT_LABEL = "PNG / JPEG / WebP";
export const ACCEPT_ATTRIBUTE = ACCEPTED_MIMES.join(",");

export function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000) {
    return `${(bytes / 1_000_000).toFixed(1)}MB`;
  }
  if (bytes >= 1000) {
    return `${Math.round(bytes / 1000)}KB`;
  }
  return `${bytes}B`;
}

/** Exact byte count of a data URL's payload, without decoding it. */
export function dataUrlBytes(dataUrl: string): number {
  const comma = dataUrl.indexOf(",");
  if (comma < 0) {
    return 0;
  }
  const payload = dataUrl.slice(comma + 1);
  const padding = payload.endsWith("==") ? 2 : payload.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor((payload.length * 3) / 4) - padding);
}

export function mimeOf(dataUrl: string): string {
  const match = /^data:([^;,]+)[;,]/.exec(dataUrl);
  return match ? match[1].toLowerCase() : "";
}

export function totalBytes(list: ChatImage[]): number {
  return list.reduce((sum, item) => sum + dataUrlBytes(item.dataUrl), 0);
}

/**
 * Why this file cannot be attached, or `null` if it can.
 *
 * Says what is wrong and what is allowed — "格式不支持" alone leaves the user
 * guessing whether to convert, crop, or give up.
 */
export function checkCandidate(candidate: ImageCandidate): string | null {
  const type = String(candidate.type || "").toLowerCase();
  if (!type) {
    return "无法识别这个文件的类型，请使用 " + ACCEPT_LABEL + " 图片";
  }
  if (!ACCEPTED_MIMES.includes(type)) {
    return `${type.replace("image/", "").toUpperCase() || type} 格式不支持，请使用 ${ACCEPT_LABEL}`;
  }
  if (candidate.size > MAX_IMAGE_BYTES) {
    return `这张图片 ${formatBytes(candidate.size)}，单张上限 ${formatBytes(MAX_IMAGE_BYTES)}`;
  }
  return null;
}

/**
 * Add an image to the pending list, or explain why it was refused.
 *
 * Pure: returns the new list so the caller decides when to render. Re-adding the
 * same image twice is refused rather than silently duplicated — pasting the same
 * screenshot twice is almost always a mistake, and a duplicate costs tokens.
 */
export function addImage(
  list: ChatImage[],
  image: ChatImage,
): { list: ChatImage[]; error: string | null } {
  if (!image.dataUrl.startsWith("data:image/")) {
    return { list, error: "这张图片没有读到内容，请重新选择或粘贴" };
  }
  const mime = mimeOf(image.dataUrl);
  if (!ACCEPTED_MIMES.includes(mime)) {
    return {
      list,
      error: `${mime.replace("image/", "").toUpperCase() || "该"} 格式不支持，请使用 ${ACCEPT_LABEL}`,
    };
  }
  if (list.some((item) => item.dataUrl === image.dataUrl)) {
    return { list, error: "这张图片已经添加过了" };
  }
  if (list.length >= MAX_IMAGES) {
    return { list, error: `一次最多 ${MAX_IMAGES} 张图片，请先移除一张` };
  }
  const size = dataUrlBytes(image.dataUrl);
  if (size > MAX_IMAGE_BYTES) {
    return { list, error: `这张图片 ${formatBytes(size)}，单张上限 ${formatBytes(MAX_IMAGE_BYTES)}` };
  }
  const after = totalBytes(list) + size;
  if (after > MAX_TOTAL_BYTES) {
    return {
      list,
      error: `图片合计会达到 ${formatBytes(after)}，上限 ${formatBytes(MAX_TOTAL_BYTES)}`,
    };
  }
  return { list: [...list, image], error: null };
}

export function removeImage(list: ChatImage[], id: string): ChatImage[] {
  return list.filter((item) => item.id !== id);
}

export function setCaption(list: ChatImage[], id: string, caption: string): ChatImage[] {
  return list.map((item) => (item.id === id ? { ...item, caption } : item));
}

/** A short summary for the send button and the notice line. */
export function describeImages(list: ChatImage[]): string {
  if (!list.length) {
    return "";
  }
  const named = list.filter((item) => item.caption.trim()).length;
  const size = formatBytes(totalBytes(list));
  return named
    ? `${list.length} 张图（${named} 张有说明）· ${size}`
    : `${list.length} 张图 · ${size}`;
}
