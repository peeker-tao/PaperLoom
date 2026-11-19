"""Model selection: the picker must reach the provider, and only real models.

The bug these guard: the sidebar's model picker only changed local state, and
`ask` never put the model in the request body, so every question ran on
`settings.chat_model` while the UI showed the chosen one. The service side was
already capable — `ChatRequest.model` overrode the default and the resolved model
came back in the `done` event and was stored on the message — so the tests below
pin the contract at both ends: a request that names a model gets that model, and
a name the service cannot run is rejected with a message that lists the choices
instead of failing later at the provider.
"""

from __future__ import annotations

from paperloom_service.app import SUPPORTED_MODEL_IDS
from tests.conftest import parse_sse, register


async def test_chat_uses_the_requested_model(client, pdf_path):
    """An explicit model must be forwarded, echoed back and stored."""
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    wanted = "deepseek-v4-pro"
    assert wanted in SUPPORTED_MODEL_IDS

    response = await client.post(
        "/v1/chat",
        json={
            "documentId": doc_id,
            "scope": "paper",
            "model": wanted,
            "messages": [{"role": "user", "content": "这篇论文的方法是什么？"}],
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    done = events[-1][1]
    assert events[-1][0] == "done"
    # The answer records what actually ran, which is what the message header shows.
    assert done["model"] == wanted

    conversations = (
        await client.get("/v1/conversations", params={"documentId": doc_id})
    ).json()
    conv_id = conversations["conversations"][0]["id"]
    messages = (await client.get(f"/v1/conversations/{conv_id}/messages")).json()[
        "messages"
    ]
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["model"] == wanted


async def test_chat_without_a_model_uses_the_configured_default(client, pdf_path):
    """No model in the body must keep working — that is the fallback path."""
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    default = (await client.get("/v1/settings")).json()["settings"]["chat_model"]

    response = await client.post(
        "/v1/chat",
        json={
            "documentId": doc_id,
            "scope": "paper",
            "messages": [{"role": "user", "content": "总结一下"}],
        },
    )
    assert response.status_code == 200
    assert parse_sse(response.text)[-1][1]["model"] == default


async def test_chat_rejects_an_unknown_model(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "documentId": doc_id,
            "scope": "paper",
            "model": "deepseek-nonexistent",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "unknown_model"
    # The message names what *is* available, so the user can fix it in place.
    for model_id in SUPPORTED_MODEL_IDS:
        assert model_id in detail["message"]


async def test_analysis_rejects_an_unknown_model(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/analysis",
        json={"kind": "card", "documentIds": [doc_id], "model": "gpt-nope"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_model"
    assert "分析模型" in response.json()["detail"]["message"]


async def test_translation_rejects_an_unknown_model(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/jobs", json={"documentId": doc_id, "model": "deepseek-nonexistent"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_model"
    assert "翻译模型" in response.json()["detail"]["message"]


async def test_settings_reject_an_unknown_model(client):
    response = await client.post("/v1/settings", json={"chatModel": "mystery-model"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unknown_model"


async def test_settings_keep_the_old_model_when_the_field_is_cleared(client):
    """Clearing the input must not save an empty model name."""
    before = (await client.get("/v1/settings")).json()["settings"]["chat_model"]
    response = await client.post("/v1/settings", json={"chatModel": "  "})
    assert response.status_code == 200
    after = (await client.get("/v1/settings")).json()["settings"]["chat_model"]
    assert after == before


async def test_settings_list_exactly_the_supported_models(client):
    """The picker and the validator must not drift apart."""
    body = (await client.get("/v1/settings")).json()
    assert [model["id"] for model in body["models"]] == list(SUPPORTED_MODEL_IDS)
    assert all(model["label"] for model in body["models"])
