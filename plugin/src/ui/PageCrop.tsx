import { useEffect, useRef, useState } from "react";
import { debug } from "../log";
import type { ReaderController } from "../reader/controller";
import { pageRect } from "./overlay";

/** Rendered page width used for crops: enough detail for a figure, still fast. */
const CROP_WIDTH = 1400;
/** Wider render for the zoom overlay: the whole point is to see the detail. */
const ZOOM_WIDTH = 2400;

type CropState =
  | { kind: "loading" }
  | { kind: "ready"; src: string }
  | { kind: "failed"; reason: string };

/**
 * A picture cut out of the PDF page.
 *
 * The reading view is reflowed text, so figures cannot be laid out "in place".
 * The service renders the region with pdfium and returns a PNG: that is the
 * primary path, because it does not depend on the reader's internal pdf.js
 * state (which is what used to leave every figure showing "图片需要回到 PDF
 * 查看"). Cropping the reader's own bitmap stays as the fallback for when the
 * service cannot render.
 *
 * When both paths fail the reason is shown, not just a shrug: "本页无法渲染"
 * gave the user nothing to act on, and the two failures have very different
 * causes (the service is down vs. the reader cannot reach pdf.js).
 */
export function PageCrop(props: {
  controller: ReaderController;
  page: number;
  bbox: [number, number, number, number];
  alt: string;
  onOpen(): void;
}): JSX.Element {
  const { controller, page, bbox, alt, onOpen } = props;
  const [state, setState] = useState<CropState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [zoom, setZoom] = useState(false);
  const key = `${page}:${bbox.join(":")}`;

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });

    const fromService = async (): Promise<string | null> => {
      const documentId = controller.state.document?.id;
      if (!documentId) {
        return null;
      }
      try {
        const blob = await controller.client.pageImage(documentId, page, {
          width: CROP_WIDTH,
          bbox,
        });
        if (cancelled) {
          return null;
        }
        // A data URL rather than a blob: URL. The sidebar lives in Zotero's
        // reader iframe, whose CSP decides what an <img> may load; a blob URL
        // that gets blocked fails silently and leaves an empty box. data: is
        // allowed everywhere the reader runs, and it survives the component
        // unmounting (no revoke to get wrong).
        return await toDataUrl(blob);
      } catch (error) {
        debug("figure render via service failed", page, String(error));
        return null;
      }
    };

    const fromReader = async (): Promise<{ src: string } | { reason: string }> => {
      const rendered = await controller.loadPageImage(page, CROP_WIDTH);
      if (cancelled) {
        return { reason: "" };
      }
      if (!rendered) {
        return { reason: "阅读器没有提供这一页的位图" };
      }
      const image = await decodeImage(rendered.dataUrl);
      if (!image) {
        return { reason: "这一页的位图无法解码" };
      }
      const rect = pageRect(bbox, rendered, image.naturalWidth);
      if (!rect) {
        // `pageRect` refuses rotated or degenerate pages: the coordinates would
        // land somewhere plausible but wrong, which is worse than saying so.
        return { reason: `本页的坐标无法直接裁切（页码 ${page}，旋转或尺寸异常）` };
      }
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(rect.width));
      canvas.height = Math.max(1, Math.round(rect.height));
      const context = canvas.getContext("2d");
      if (!context) {
        return { reason: "浏览器拒绝创建画布" };
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
      return { src: canvas.toDataURL("image/png") };
    };

    void (async () => {
      const served = await fromService();
      if (cancelled) {
        return;
      }
      if (served) {
        setState({ kind: "ready", src: served });
        return;
      }
      const local = await fromReader();
      if (cancelled) {
        return;
      }
      if ("src" in local) {
        setState({ kind: "ready", src: local.src });
        return;
      }
      setState({
        kind: "failed",
        reason: local.reason || "本地服务没有返回这张图片",
      });
    })();

    return () => {
      cancelled = true;
    };
    // `key` covers page and bbox; `attempt` is the retry counter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  if (state.kind === "failed") {
    return (
      <div className="pl-md__figure-failed">
        <div className="pl-small">{state.reason || "这张图片没能渲染出来"}</div>
        <div className="pl-actions">
          <button type="button" className="pl-btn pl-btn--ghost" onClick={() => setAttempt((n) => n + 1)}>
            重试
          </button>
          <button type="button" className="pl-btn pl-btn--ghost" onClick={onOpen}>
            在 PDF 中查看
          </button>
        </div>
      </div>
    );
  }
  if (state.kind === "loading") {
    return <div className="pl-md__figure-loading">正在截取原文图片…</div>;
  }
  return (
    <>
      <img
        className="pl-md__figure-img"
        src={state.src}
        alt={alt}
        title={`${alt} · 点击放大`}
        // Without this a rejected image (blocked by CSP, truncated response)
        // showed an empty box: the state stayed "ready", so the user got neither
        // the picture nor the "回到 PDF 查看" button.
        onError={() => {
          debug("figure image failed to load", page, bbox.join(","));
          setState({ kind: "failed", reason: "图片数据已拿到，但浏览器拒绝显示它" });
        }}
        onClick={() => setZoom(true)}
      />
      {zoom ? (
        <FigureZoom
          controller={controller}
          page={page}
          bbox={bbox}
          alt={alt}
          fallback={state.src}
          onClose={() => setZoom(false)}
          onOpen={() => {
            setZoom(false);
            onOpen();
          }}
        />
      ) : null}
    </>
  );
}

/**
 * Full-size view of one figure.
 *
 * Reads the same region at a much higher width instead of upscaling the
 * thumbnail: a figure that is illegible in the column is usually illegible
 * because it was rendered small, not because the screen is small.
 */
function FigureZoom(props: {
  controller: ReaderController;
  page: number;
  bbox: [number, number, number, number];
  alt: string;
  fallback: string;
  onClose(): void;
  onOpen(): void;
}): JSX.Element {
  const { controller, page, bbox, alt, fallback, onClose, onOpen } = props;
  const [src, setSrc] = useState<string>(fallback);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string>("");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    const documentId = controller.state.document?.id;
    if (!documentId) {
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const blob = await controller.client.pageImage(documentId, page, {
          width: ZOOM_WIDTH,
          bbox,
        });
        if (cancelled) {
          return;
        }
        const hi = await toDataUrl(blob);
        if (!cancelled && hi) {
          setSrc(hi);
        }
      } catch (error) {
        // The thumbnail is still on screen, so a failed hi-res render degrades
        // to "less detail", not to "no picture".
        debug("figure zoom render failed", page, String(error));
        if (!cancelled) {
          setNote("高清版本没有取到，显示的是较低分辨率");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, bbox.join(":")]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  return (
    <div className="pl-zoom" role="dialog" aria-label="图片放大" onClick={onClose}>
      <div className="pl-zoom__panel" onClick={(event) => event.stopPropagation()}>
        <div className="pl-zoom__bar">
          <span className="pl-small pl-muted">
            第 {page} 页{loading ? " · 正在取高清图…" : ""}
            {note ? ` · ${note}` : ""}
          </span>
          <div className="pl-row">
            <button type="button" className="pl-btn pl-btn--ghost pl-small" onClick={onOpen}>
              查看原页
            </button>
            <button
              ref={closeRef}
              type="button"
              className="pl-btn pl-btn--ghost pl-small"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </div>
        <div className="pl-zoom__canvas">
          <img src={src} alt={alt} />
        </div>
      </div>
    </div>
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
