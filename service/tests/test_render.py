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
