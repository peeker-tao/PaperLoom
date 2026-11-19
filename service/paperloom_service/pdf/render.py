"""Render pages (or a region of a page) to PNG for the reading view.

The plugin used to crop figures out of the bitmap that pdf.js produced inside
the reader iframe. That failed in Zotero for reasons the user cannot see
(`PDFViewerApplication.pdfDocument` not ready, a render that never resolves), and
the fallback message — "图片需要回到 PDF 查看" — is exactly what a missing feature
looks like. The service already has the PDF and pdfium is a single wheel, so
rendering here removes the dependency on the reader's internal state entirely.

Coordinates are PDF user space with the origin at the bottom-left, the same space
the parser reports bounding boxes in.
"""

from __future__ import annotations

import importlib.util
import io
import threading
from collections import OrderedDict
from pathlib import Path

# Width used when the caller does not ask for one: enough detail for a figure,
# small enough to transfer over loopback without a noticeable delay.
DEFAULT_WIDTH = 1400
MIN_WIDTH = 200
MAX_WIDTH = 2400
# pdfium refuses absurd scales; keep the page inside a sane bitmap.
MAX_SCALE = 4.0

# pdfium is not thread-safe, and a request handler is not the only thread that
# can reach it: FastAPI runs every `def` endpoint on a worker thread, so a page
# with several figures issues several renders at once. Two threads inside
# pdfium do not raise — they crash the process (observed: the whole service
# disappeared mid-read, leaving only TIME_WAIT sockets and no traceback, so the
# plugin then failed with "connection refused" on every later call, including
# translation). One lock for the module is the cheapest correct fix.
_PDFIUM_LOCK = threading.Lock()

# Rendering is the most expensive thing the service does on a read path, and the
# plugin asks for the same few crops again whenever the sidebar re-renders.
# Bounded so a long document cannot grow it without limit.
_CACHE_MAX = 24
_cache: OrderedDict[tuple, bytes] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(
    path: Path,
    page: int,
    width: int,
    bbox: tuple[float, float, float, float] | None,
) -> tuple:
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = (0, 0)
    return (str(path), stamp, page, width, bbox)


def _cached(key: tuple) -> bytes | None:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _store(key: tuple, data: bytes) -> None:
    with _cache_lock:
        _cache[key] = data
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def clear_cache() -> None:
    """Drop rendered pages (used by tests and after a document is replaced)."""
    with _cache_lock:
        _cache.clear()


def render_available() -> bool:
    return importlib.util.find_spec("pypdfium2") is not None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def render_page_png(
    path: Path,
    page: int,
    *,
    width: int = DEFAULT_WIDTH,
    bbox: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Render one page, or the ``bbox`` region of it, as PNG bytes."""
    if not render_available():
        raise RuntimeError("pypdfium2 未安装")
    key = _cache_key(Path(path), page, width, bbox)
    hit = _cached(key)
    if hit is not None:
        return hit
    data = _render_uncached(Path(path), page, width=width, bbox=bbox)
    _store(key, data)
    return data


def _render_uncached(
    path: Path,
    page: int,
    *,
    width: int,
    bbox: tuple[float, float, float, float] | None,
) -> bytes:
    import pypdfium2 as pdfium  # imported lazily: optional dependency

    with _PDFIUM_LOCK:
        document = pdfium.PdfDocument(str(path))
        try:
            if page < 1 or page > len(document):
                raise ValueError(f"页码超出范围：{page}")
            pdf_page = document[page - 1]
            size_width, size_height = pdf_page.get_size()
            if not size_width or not size_height:
                raise ValueError("无法读取页面尺寸")
            rotation = int(pdf_page.get_rotation() or 0) % 360
            # `get_size()` reports the page *as displayed*, so for a rotated page
            # the reported width is the unrotated height. Both are needed: the
            # scale comes from the displayed width, the crop from the unrotated
            # frame (which is where pdfminer's bboxes live).
            if rotation in (90, 270):
                page_width, page_height = size_height, size_width
            else:
                page_width, page_height = size_width, size_height
            # A crop is rendered at a higher scale than a whole page: the region
            # is small, so the same pixel width means more detail.
            requested = _clamp(float(width or DEFAULT_WIDTH), MIN_WIDTH, MAX_WIDTH)
            scale = _clamp(requested / page_width, 0.2, MAX_SCALE)
            if bbox:
                # Width of the requested region *after* rotation: for a quarter
                # turn the visual width is the unrotated height.
                if rotation in (90, 270):
                    region_width = max(1.0, bbox[3] - bbox[1])
                else:
                    region_width = max(1.0, bbox[2] - bbox[0])
                scale = _clamp(requested / region_width, 0.2, MAX_SCALE)
            bitmap = pdf_page.render(scale=scale)
            image = bitmap.to_pil()
            if bbox:
                left, top, right, bottom = _crop_box(
                    bbox,
                    page_width=page_width,
                    page_height=page_height,
                    rotation=rotation,
                    scale=scale,
                )
                left = max(0, left)
                top = max(0, top)
                right = min(image.width, right)
                bottom = min(image.height, bottom)
                if right - left < 2 or bottom - top < 2:
                    raise ValueError("裁切区域过小")
                image = image.crop((left, top, right, bottom))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            document.close()


def _crop_box(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    rotation: int,
    scale: float,
) -> tuple[int, int, int, int]:
    """Map a bbox in PDF space onto pixel coordinates of the rendered bitmap.

    Two coordinate changes happen between a text bbox and a pixel:

    * PDF space grows upwards, bitmaps grow downwards.
    * A page may carry ``/Rotate``. pdfium renders it upright — so for a page
      rotated 90° the bitmap is *taller* than it is wide, while the bbox (which
      comes from pdfminer, which ignores rotation) is still expressed in the
      unrotated frame.

    The previous version assumed rotation 0. On a rotated page that did not fail
    loudly: it cropped a plausible-looking rectangle out of the wrong place, so a
    figure appeared as an unrelated strip of the page. The four cases below were
    measured against real renders rather than derived on paper.

    ``page_width``/``page_height`` are the *unrotated* size; ``scale`` turns PDF
    units into pixels.
    """
    x0, y0, x1, y1 = bbox
    turned = rotation % 360
    if turned == 90:
        left, top, right, bottom = y0, x0, y1, x1
    elif turned == 180:
        left, top, right, bottom = page_width - x1, y0, page_width - x0, y1
    elif turned == 270:
        left, top, right, bottom = page_height - y1, page_width - x1, page_height - y0, page_width - x0
    else:
        left, top, right, bottom = x0, page_height - y1, x1, page_height - y0
    return (
        round(left * scale),
        round(top * scale),
        round(right * scale),
        round(bottom * scale),
    )


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Parse the ``bbox=x0,y0,x1,y1`` query parameter."""
    if not raw:
        return None
    parts = [piece.strip() for piece in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox 需要 4 个数字：x0,y0,x1,y1")
    try:
        x0, y0, x1, y1 = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox 必须是数字") from exc
    if not (x1 > x0 and y1 > y0):
        raise ValueError("bbox 必须满足 x1>x0 且 y1>y0")
    return (x0, y0, x1, y1)
