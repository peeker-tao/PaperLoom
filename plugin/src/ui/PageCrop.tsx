import { useEffect, useState } from "react";
import { debug } from "../log";
import type { ReaderController } from "../reader/controller";
import { pageRect } from "./overlay";

/** Rendered page width used for crops: enough detail for a figure, still fast. */
const CROP_WIDTH = 1400;

/**
 * A picture cut out of the PDF page.
 *
 * The reading view is reflowed text, so figures cannot be laid out "in place".
 * The service renders the region with pdfium and returns a PNG: that is the
 * primary path, because it does not depend on the reader's internal pdf.js
 * state (which is what used to leave every figure showing "图片需要回到 PDF
 * 查看"). Cropping the reader's own bitmap stays as the fallback for when the
 * service cannot render.
 */
export function PageCrop(props: {
  controller: ReaderController;
  page: number;
  bbox: [number, number, number, number];
  alt: string;
  onOpen(): void;
}): JSX.Element {
  const { controller, page, bbox, alt, onOpen } = props;
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const key = `${page}:${bbox.join(":")}`;

  useEffect(() => {
    let cancelled = false;
    setSrc(null);
    setFailed(false);

    const fromService = async (): Promise<boolean> => {
      const documentId = controller.state.document?.id;
      if (!documentId) {
        return false;
      }
      try {
        const blob = await controller.client.pageImage(documentId, page, {
          width: CROP_WIDTH,
          bbox,
        });
        if (cancelled) {
          return true;
        }
        // A data URL rather than a blob: URL. The sidebar lives in Zotero's
        // reader iframe, whose CSP decides what an <img> may load; a blob URL
        // that gets blocked fails silently and leaves an empty box. data: is
        // allowed everywhere the reader runs, and it survives the component
        // unmounting (no revoke to get wrong).
        setSrc(await toDataUrl(blob));
        return true;
      } catch (error) {
        debug("figure render via service failed", page, String(error));
        return false;
      }
    };

    const fromReader = async (): Promise<void> => {
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
        setSrc(canvas.toDataURL("image/png"));
      }
    };

    void (async () => {
      if (!(await fromService())) {
        await fromReader();
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
        图片需要回到 PDF 查看（本页无法渲染）
      </button>
    );
  }
  if (!src) {
    return <div className="pl-md__figure-loading">正在截取原文图片…</div>;
  }
  return (
    <img
      className="pl-md__figure-img"
      src={src}
      alt={alt}
      title={`${alt} · 点击定位到 PDF 原页`}
      // Without this a rejected image (blocked by CSP, truncated response)
      // showed an empty box: `failed` stayed false, so the user got neither the
      // picture nor the "回到 PDF 查看" button.
      onError={() => {
        debug("figure image failed to load", page, bbox.join(","));
        setFailed(true);
      }}
      onClick={onOpen}
    />
  );
}

/** Read a blob as a data URL (`blob:` URLs are not reliably allowed in the reader). */
function toDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(blob);
  });
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
