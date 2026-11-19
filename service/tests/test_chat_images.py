"""Asking about a picture: validation, capability, and surviving a reload.

The composer accepts images now, which means three things can go wrong that used
to be impossible: an image the provider will not take, an image sent to a model
that cannot see, and an image that disappears the moment the paper is reopened.
Each gets its own test.

The tiny PNG below is a real 1x1 transparent image, so the check is on the actual
payload shape rather than a made-up string.
"""

from __future__ import annotations

import base64

from paperloom_service.app import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    attach_images,
    image_problem,
    model_supports_vision,
)
from tests.conftest import parse_sse, register

PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AARAA"
        "B/gG0EQAAAABJRU5ErkJggg=="
    )
).decode()
URL = f"data:image/png;base64,{PNG}"


# ---------------------------------------------------------------- validation


def test_a_normal_image_is_accepted():
    assert image_problem([URL]) is None


def test_no_images_is_accepted():
    assert image_problem([]) is None


def test_too_many_images_is_refused():
    assert "最多" in (image_problem([URL] * (MAX_IMAGES + 1)) or "")


def test_a_non_data_url_is_refused():
    """A failed paste produces a bare path or an `blob:` URL, not base64."""
    assert "数据" in (image_problem(["blob:http://x/abc"]) or "")


def test_an_unsupported_format_is_refused():
    problem = image_problem(["data:image/bmp;base64,AAAA"]) or ""
    assert "BMP" in problem or "bmp" in problem


def test_an_oversized_image_is_refused():
    huge = (
        "data:image/png;base64,"
        + base64.b64encode(b"x" * (MAX_IMAGE_BYTES + 10)).decode()
    )
    assert "上限" in (image_problem([huge]) or "")


def test_a_caption_is_sent_alongside_the_image():
    """The caption has to travel with the picture, or "图 2" means nothing."""
    messages = [{"role": "user", "content": "这两张图有什么区别"}]
    attach_images(
        messages, ["data:image/png;base64,AA", "data:image/png;base64,BB"], ["左图", ""]
    )
    parts = messages[0]["content"]
    assert parts[0] == {"type": "text", "text": "这两张图有什么区别"}
    assert {"type": "text", "text": "（图 1：左图）"} in parts
    assert sum(1 for part in parts if part["type"] == "image_url") == 2


def test_attachment_order_is_preserved():
    messages = [{"role": "user", "content": "q"}]
    attach_images(
        messages, ["data:image/png;base64,AAA", "data:image/png;base64,BBB"], []
    )
    urls = [
        part["image_url"]["url"]
        for part in messages[0]["content"]
        if part["type"] == "image_url"
    ]
    assert urls == ["data:image/png;base64,AAA", "data:image/png;base64,BBB"]


def test_vision_capability_matches_the_model_list():
    assert model_supports_vision("deepseek-flash")
    assert not model_supports_vision("deepseek-v4-pro")
    assert not model_supports_vision(None)


# ------------------------------------------------------------------ endpoint


def _chat_body(doc_id: str, **extra) -> dict:
    return {
        "documentId": doc_id,
        "scope": "paper",
        "messages": [{"role": "user", "content": "解释一下这张图"}],
        **extra,
    }


async def test_an_image_is_refused_by_a_model_that_cannot_see_it(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    response = await client.post(
        "/v1/chat",
        json=_chat_body(doc["id"], model="deepseek-v4-pro", images=[{"dataUrl": URL}]),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "model_no_vision"


async def test_an_invalid_image_is_refused_before_the_model_is_called(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    response = await client.post(
        "/v1/chat",
        json=_chat_body(doc["id"], model="deepseek-flash", images=[{"dataUrl": "x"}]),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "image_invalid"


async def test_the_legacy_single_image_still_works(client, pdf_path):
    """Figure annotations send `image`, and must keep working."""
    doc = (await register(client, pdf_path))["document"]
    response = await client.post(
        "/v1/chat", json=_chat_body(doc["id"], model="deepseek-flash", image=URL)
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert any(name == "done" for name, _ in events)


async def test_the_question_keeps_its_image_after_a_reload(client, pdf_path):
    doc = (await register(client, pdf_path))["document"]
    body = _chat_body(
        doc["id"],
        model="deepseek-flash",
        images=[{"id": "i1", "dataUrl": URL, "caption": "结果图"}],
    )
    first = parse_sse((await client.post("/v1/chat", json=body)).text)
    conversation_id = next(
        data["conversationId"] for name, data in first if name == "context"
    )

    restored = (
        await client.get(f"/v1/conversations/{conversation_id}/messages")
    ).json()
    asked = [m for m in restored["messages"] if m["role"] == "user"][-1]
    assert asked["attachments"][0]["caption"] == "结果图"
    assert asked["attachments"][0]["dataUrl"] == URL
