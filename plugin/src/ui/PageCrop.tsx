import { useEffect, useState } from "react";
import type { ReaderController } from "../reader/controller";
import { pageRect } from "./overlay";

/** Rendered page width used for crops: enough detail for a figure, still fast. */
const CROP_WIDTH = 1200;

/**
 * A picture cut out of the PDF page.
 *
 * The reading view is reflowed text, so figures cannot be laid out "in place".
 * Instead the page is rendered once (the controller caches it) and the region
 * belonging to the figure — computed by the service from the caption's box —
 * is cropped out of that bitmap. The result is the real picture: exact
 * colours, axes, sub-labels, everything a re-typeset SVG would lose.
 */
export function PageCrop(props: {
  controller: ReaderController;
  page: number;
  bbox: [number, number, number, number];
  alt: string;
  onOpen(): void;
}): JSX.Element {
  const { controller, page, bbox, alt, onOpen } = props;
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const key = `${page}:${bbox.join(":")}`;

  useEffect(() => {
    let cancelled = false;
    setUrl(null);
    setFailed(false);
    void (async () => {
      const rendered = await controller.loadPageImage(page, CROP_WIDTH);
      if (cancelled) {
        return;
      }
      if (!rendered) {
        setFailed(true);
        return;
      }
      const image = await decodeImage(rendered.dataUrl);
      if (cancelled) {
        return;
      }
      if (!image) {
        setFailed(true);
        return;
      }
      const rect = pageRect(bbox, rendered, image.naturalWidth);
      if (!rect) {
        setFailed(true);
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(rect.width));
      canvas.height = Math.max(1, Math.round(rect.height));
      const context = canvas.getContext("2d");
      if (!context) {
        setFailed(true);
        return;
      }
      context.drawImage(
        image,
        rect.left,
        rect.top,
        rect.width,
        rect.height,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      if (!cancelled) {
        setUrl(canvas.toDataURL("image/png"));
      }
    })();
    return () => {
      cancelled = true;
    };
    // `key` covers page and bbox; the controller instance is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (failed) {
    return (
      <button type="button" className="pl-md__figure-fallback" onClick={onOpen}>
        图片需要回到 PDF 查看（无法渲染本页）
      </button>
    );
  }
  if (!url) {
    return <div className="pl-md__figure-loading">正在截取原文图片…</div>;
  }
  return (
    <img
      className="pl-md__figure-img"
      src={url}
      alt={alt}
      title={`${alt} · 点击定位到 PDF 原页`}
      onClick={onOpen}
    />
  );
}

/** Decode a data URL into an image, tolerating a decode failure. */
async function decodeImage(dataUrl: string): Promise<HTMLImageElement | null> {
  const image = document.createElement("img");
  const loaded = new Promise<boolean>((resolve) => {
    image.onload = () => resolve(true);
    image.onerror = () => resolve(false);
  });
  image.src = dataUrl;
  if (!(await loaded)) {
    return null;
  }
  try {
    await image.decode?.();
  } catch {
    // Some builds throw when the image is already decoded; it is usable.
  }
  return image.naturalWidth > 0 ? image : null;
}
