"""Server-side page rendering: this is what puts figures back in the reading view.

The plugin used to crop figures from the reader's own pdf.js bitmap, which is not
reliably reachable from the sidebar inside Zotero — every figure showed
"图片需要回到 PDF 查看". Rendering in the service removes that dependency.
"""

from __future__ import annotations

import pytest

from tests.conftest import register

pytest.importorskip("pypdfium2")
pytest.importorskip("PIL")


def png_size(data: bytes) -> tuple[int, int]:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(data)) as image:
        return image.size


async def test_renders_a_whole_page(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    response = await client.get(f"/v1/documents/{doc['id']}/page/1.png?width=600")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = png_size(response.content)
    # The fixture page is US Letter: portrait, scaled to the requested width.
    assert 500 <= width <= 700
    assert height > width


async def test_bbox_returns_only_that_region(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    whole = await client.get(f"/v1/documents/{doc['id']}/page/1.png?width=600")
    region = await client.get(
        f"/v1/documents/{doc['id']}/page/1.png?width=600&bbox=40,600,260,700"
    )
    assert region.status_code == 200
    _whole_w, whole_h = png_size(whole.content)
    crop_w, crop_h = png_size(region.content)
    # `width` is the output width, so a crop comes back exactly that wide.
    assert crop_w == pytest.approx(600, abs=2)
    assert crop_h < whole_h
    # 220x100 points of page keep their aspect ratio.
    assert crop_w / crop_h == pytest.approx(220 / 100, rel=0.05)


async def test_rejects_a_malformed_bbox(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    for bad in ("1,2,3", "1,2,3,4,5", "a,b,c,d", "100,100,0,0"):
        response = await client.get(f"/v1/documents/{doc['id']}/page/1.png?bbox={bad}")
        assert response.status_code == 400, bad
        assert response.json()["detail"]["code"] == "bad_bbox"


async def test_rejects_a_page_outside_the_document(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    response = await client.get(f"/v1/documents/{doc['id']}/page/99.png")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "render_failed"


async def test_unknown_document_is_404(client):
    response = await client.get("/v1/documents/does-not-exist/page/1.png")
    assert response.status_code == 404


async def test_capability_is_reported(client):
    body = (await client.get("/v1/status")).json()
    assert body["capabilities"]["render"]["available"] is True


def test_concurrent_renders_do_not_crash_pdfium(pdf_path):
    """Regression: pdfium is not thread-safe and used to take the service down.

    FastAPI runs every `def` endpoint on a worker thread, so a page with several
    figures asks for several renders at once. Two threads inside pdfium do not
    raise — they kill the process. Observed live: the service vanished mid-read
    leaving only TIME_WAIT sockets and no traceback, after which every call
    (including 翻译) failed with "connection refused".
    """
    from concurrent.futures import ThreadPoolExecutor

    from paperloom_service.pdf.render import clear_cache, render_page_png

    clear_cache()
    jobs = [(1, None), (2, None), (1, (40.0, 600.0, 260.0, 700.0))] * 4

    def run(job):
        page, box = job
        return render_page_png(pdf_path, page, width=600, bbox=box)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, jobs))
    assert len(results) == len(jobs)
    assert all(data.startswith(b"\x89PNG\r\n\x1a\n") for data in results)
    # Every page-1 render is the same crop; sizes must agree even though pdfium's
    # anti-aliasing is not bit-for-bit deterministic across runs.
    assert len({len(data) for data in results[0::3]}) == 1


def test_identical_requests_are_served_from_the_cache(pdf_path):
    """The sidebar re-asks for the same crops on every re-render; do not redo work."""
    from paperloom_service.pdf.render import clear_cache, render_page_png

    clear_cache()
    first = render_page_png(pdf_path, 1, width=600)
    second = render_page_png(pdf_path, 1, width=600)
    assert first == second
    # A different width is a different bitmap, not a cache hit.
    other = render_page_png(pdf_path, 1, width=800)
    assert other != first


# ------------------------------------------------------------------ rotation

# A 200x100 page with a red block at PDF coordinates (10..30, 10..30) — the
# bottom-left corner in PDF space. Cropping that bbox must return a red picture
# whatever the page rotation, which is the only check that can tell "the crop
# followed the rotation" from "the crop landed somewhere plausible".
MARKER_PAGE = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]%(rot)s/Contents 4 0 R>>endobj
4 0 obj<</Length 29>>stream
1 0 0 rg 10 10 20 20 re f
endstream
endobj
trailer<</Root 1 0 R>>
"""


def marker_pdf(path, rotation: int):
    body = MARKER_PAGE.replace(b"%(rot)s", f"/Rotate {rotation}".encode())
    path.write_bytes(body)
    return path


def redness(png: bytes) -> float:
    """Share of pixels that are strongly red (the marker) in a rendered crop."""
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(png)) as image:
        pixels = list(image.convert("RGB").getdata())
    red = sum(1 for r, g, b in pixels if r > 120 and g < 100 and b < 100)
    return red / max(1, len(pixels))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_a_crop_follows_the_page_rotation(tmp_path, rotation):
    from paperloom_service.pdf.render import clear_cache, render_page_png

    clear_cache()
    path = marker_pdf(tmp_path / f"rot{rotation}.pdf", rotation)
    crop = render_page_png(path, 1, width=200, bbox=(10.0, 10.0, 30.0, 30.0))
    assert redness(crop) > 0.9, f"rotation {rotation}: the crop missed the marker"


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_a_crop_of_empty_space_stays_empty(tmp_path, rotation):
    """The other half of the check: rotation must not make white areas red."""
    from paperloom_service.pdf.render import clear_cache, render_page_png

    clear_cache()
    path = marker_pdf(tmp_path / f"rot{rotation}.pdf", rotation)
    crop = render_page_png(path, 1, width=200, bbox=(100.0, 40.0, 160.0, 90.0))
    assert redness(crop) < 0.01, f"rotation {rotation}: the crop caught the marker"


def test_a_rotated_page_can_be_rendered_whole(tmp_path):
    from paperloom_service.pdf.render import clear_cache, render_page_png

    clear_cache()
    path = marker_pdf(tmp_path / "rot90.pdf", 90)
    whole = render_page_png(path, 1, width=200)
    width, height = png_size(whole)
    # Rotated 90 degrees, the 200x100 page displays as 100x200.
    assert height > width
