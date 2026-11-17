"""End-to-end service tests using a fake LLM transport (no network)."""

from __future__ import annotations

import pytest

from tests.conftest import parse_sse, register, wait_job
from tests.fixtures import scanned_pdf


async def test_health_without_token(client):
    response = await client.get("/health", headers={})
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "paperloom"
    assert body["version"]


async def test_auth_required(client):
    response = await client.get("/v1/status", headers={"x-paperloom-token": ""})
    assert response.status_code == 401
    response = await client.get("/v1/status", headers={"x-paperloom-token": "wrong"})
    assert response.status_code == 401
    response = await client.get(
        "/v1/status", headers={"x-paperloom-token": "", "authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


async def test_status_and_settings(client):
    response = await client.get("/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["apiKey"]["configured"] is False
    assert body["capabilities"]["babeldoc"]["license"] == "AGPL-3.0"

    response = await client.get("/v1/settings")
    settings = response.json()
    assert settings["settings"]["base_url"] == "https://api.deepseek.com"
    assert "apiKey" not in settings["settings"]
    assert any(m["id"] == "deepseek-flash" for m in settings["models"])
    check = settings["baseUrlCheck"]
    assert check["ok"] is True
    assert check["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert check["sdkBase"] == "https://api.deepseek.com/v1"


async def test_settings_normalizes_base_url(client):
    response = await client.post(
        "/v1/settings", json={"baseUrl": "https://api.deepseek.com/v1/"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["settings"]["base_url"] == "https://api.deepseek.com/v1"
    assert body["baseUrlCheck"]["endpoint"] == "https://api.deepseek.com/v1/chat/completions"
    assert "/v1/v1" not in body["baseUrlCheck"]["endpoint"]

    response = await client.post("/v1/settings", json={"baseUrl": "https://api.deepseek.com"})
    assert response.json()["settings"]["base_url"] == "https://api.deepseek.com"


async def test_settings_rejects_invalid_base_url(client):
    response = await client.post("/v1/settings", json={"baseUrl": "ftp://example.com"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "bad_base_url"


async def test_settings_store_masks_key(client):
    response = await client.post(
        "/v1/settings", json={"apiKey": "sk-test-abcdefghijklmnop"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["apiKey"]["configured"] is True
    assert "sk-test-abcdefghijklmnop" not in response.text
    assert body["apiKey"]["hint"].startswith("sk-t")

    response = await client.post("/v1/settings", json={"apiKey": ""})
    assert response.json()["apiKey"]["configured"] is False


async def test_register_and_segments(client, pdf_path):
    data = await register(client, pdf_path)
    doc = data["document"]
    assert doc["pages"] == 2
    assert doc["alignment"] == "segment"
    assert doc["scanned"] is False
    assert data["segmentCount"] > 0

    again = await register(client, pdf_path)
    assert again["cached"] is True
    assert again["document"]["id"] == doc["id"]

    response = await client.get(f"/v1/documents/{doc['id']}/segments")
    segments = response.json()["segments"]
    assert segments
    assert segments[0]["bbox"]
    assert segments[0]["id"].startswith("p1-s")


async def test_translate_job_with_fake_llm(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]

    response = await client.post("/v1/jobs", json={"documentId": doc_id})
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]

    job = await wait_job(client, job_id)
    assert job["state"] == "succeeded", job
    assert job["progress"]["done"] == job["progress"]["total"]
    assert job["usage"]["promptTokens"] > 0
    kinds = {a["kind"] for a in job["artifacts"]}
    assert "segments" in kinds

    response = await client.get(f"/v1/documents/{doc_id}/segments")
    segments = response.json()["segments"]
    translated = [s for s in segments if s.get("translation")]
    assert translated
    assert translated[0]["translation"].startswith("【模拟译文】")

    events = await client.get(f"/v1/jobs/{job_id}/events")
    parsed = parse_sse(events.text)
    names = [name for name, _ in parsed]
    assert "progress" in names
    assert names[-1] == "done"
    assert parsed[-1][1]["state"] == "succeeded"


async def test_job_cancel_is_idempotent(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post("/v1/jobs", json={"documentId": doc_id})
    job_id = response.json()["job"]["id"]
    await wait_job(client, job_id)

    response = await client.post(f"/v1/jobs/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["job"]["state"] == "succeeded"


async def test_job_retry_creates_new_job(client, pdf_path):
    data = await register(client, pdf_path)
    job_id = (
        await client.post("/v1/jobs", json={"documentId": data["document"]["id"]})
    ).json()["job"]["id"]
    await wait_job(client, job_id)
    response = await client.post(f"/v1/jobs/{job_id}/retry")
    assert response.status_code == 200
    new_job = response.json()["job"]
    assert new_job["id"] != job_id
    await wait_job(client, new_job["id"])


async def test_scanned_pdf_job_fails_clearly(client, tmp_path):
    path = scanned_pdf(tmp_path / "scan.pdf")
    data = await register(client, path)
    assert data["document"]["scanned"] is True
    response = await client.post(
        "/v1/jobs", json={"documentId": data["document"]["id"]}
    )
    job_id = response.json()["job"]["id"]
    job = await wait_job(client, job_id)
    assert job["state"] == "failed"
    assert job["error"]["code"] == "scanned_pdf"
    assert job["error"]["retryable"] is False


async def test_chat_streams_and_persists(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "documentId": doc_id,
            "scope": "paper",
            "messages": [{"role": "user", "content": "这篇论文提出了什么方法？"}],
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert "delta" in names
    assert names[-1] == "done"
    done = events[-1][1]
    assert "模拟" in done["text"]
    citations = next(
        payload["citations"] for name, payload in events if name == "citations"
    )
    assert citations
    assert citations[0]["segmentId"]

    conversations = (
        await client.get("/v1/conversations", params={"documentId": doc_id})
    ).json()
    assert conversations["conversations"]
    conv_id = conversations["conversations"][0]["id"]
    messages = (await client.get(f"/v1/conversations/{conv_id}/messages")).json()[
        "messages"
    ]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["status"] == "done"


async def test_chat_requires_parsed_document(client, tmp_path):
    from tests.fixtures import paper_pdf

    data = await register(client, paper_pdf(tmp_path / "x.pdf"))
    doc_id = data["document"]["id"]
    # Wipe segments to simulate a registered but unparsed document.
    await client.post(f"/v1/documents/{doc_id}/reparse")
    response = await client.post(
        "/v1/chat",
        json={"documentId": "missing", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 404


async def test_chat_rejects_invalid_image(client, pdf_path):
    data = await register(client, pdf_path)
    response = await client.post(
        "/v1/chat",
        json={
            "documentId": data["document"]["id"],
            "messages": [{"role": "user", "content": "看图"}],
            "image": "not-a-data-url",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "image_invalid"


async def test_chat_accepts_image_data_url(client, pdf_path):
    import base64

    data = await register(client, pdf_path)
    image = "data:image/png;base64," + base64.b64encode(b"fake-png-bytes").decode()
    response = await client.post(
        "/v1/chat",
        json={
            "documentId": data["document"]["id"],
            "scope": "selection",
            "selection": {"text": "Figure 2: architecture", "page": 1, "kind": "figure"},
            "image": image,
            "messages": [{"role": "user", "content": "解释这个图"}],
        },
    )
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["status"] == "done"


async def test_analysis_stream(client, pdf_path):
    data = await register(client, pdf_path)
    response = await client.post(
        "/v1/analysis",
        json={
            "kind": "limitations",
            "documentIds": [data["document"]["id"]],
            "focus": "实验缺失",
        },
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[0][0] == "context"
    assert events[-1][0] == "done"
    assert events[-1][1]["status"] == "done"


async def test_glossary_crud(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/glossary",
        json={
            "documentId": doc_id,
            "source": "sparse attention",
            "target": "稀疏注意力",
        },
    )
    assert response.status_code == 200
    term = response.json()["term"]
    assert term["status"] == "confirmed"

    response = await client.patch(
        f"/v1/glossary/{term['id']}", json={"target": "稀疏注意机制"}
    )
    assert response.json()["term"]["target"] == "稀疏注意机制"

    listed = (await client.get("/v1/glossary", params={"documentId": doc_id})).json()[
        "terms"
    ]
    assert any(t["id"] == term["id"] for t in listed)

    assert (await client.delete(f"/v1/glossary/{term['id']}")).json()["deleted"] is True
    assert (await client.delete(f"/v1/glossary/{term['id']}")).status_code == 404


async def test_glossary_extract_fake(client, pdf_path):
    data = await register(client, pdf_path)
    response = await client.post(
        "/v1/glossary/extract",
        json={"documentId": data["document"]["id"], "maxTerms": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0  # fake LLM returns a non-glossary payload on purpose


async def test_translation_status_tracks_config_changes(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]

    initial = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert initial["total"] == 0
    assert initial["missing"] > 0
    assert initial["needsAttention"] is False

    await wait_job(client, (await client.post("/v1/jobs", json={"documentId": doc_id})).json()["job"]["id"])

    current = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert current["total"] > 0
    assert current["stale"] == 0
    assert current["current"] == current["total"]
    assert current["missing"] == 0

    # A different model invalidates every translation.
    changed = (
        await client.get(
            f"/v1/documents/{doc_id}/translation-status", params={"model": "deepseek-v4-pro"}
        )
    ).json()
    assert changed["stale"] == current["total"]
    assert changed["needsAttention"] is True
    assert "model" in changed["reasons"]
    assert changed["reasonsText"]


async def test_glossary_change_marks_translations_stale(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    await wait_job(client, (await client.post("/v1/jobs", json={"documentId": doc_id})).json()["job"]["id"])

    await client.post(
        "/v1/glossary",
        json={"documentId": doc_id, "source": "sparse attention", "target": "稀疏注意力"},
    )
    status = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert status["stale"] == status["total"]
    assert "glossary" in status["reasons"]


async def test_stale_only_retranslates_just_the_changed_config(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    await wait_job(client, (await client.post("/v1/jobs", json={"documentId": doc_id})).json()["job"]["id"])

    # Nothing stale: the job is a no-op instead of silently redoing everything.
    job_id = (
        await client.post("/v1/jobs", json={"documentId": doc_id, "staleOnly": True})
    ).json()["job"]["id"]
    job = await wait_job(client, job_id)
    assert job["state"] == "succeeded"
    options = job.get("options") or {}
    assert options.get("staleOnly") is True

    # Glossary change makes everything stale; staleOnly now does the work.
    await client.post(
        "/v1/glossary",
        json={"documentId": doc_id, "source": "routing network", "target": "路由网络"},
    )
    status = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert status["stale"] > 0
    job_id = (
        await client.post("/v1/jobs", json={"documentId": doc_id, "staleOnly": True})
    ).json()["job"]["id"]
    job = await wait_job(client, job_id)
    assert job["state"] == "succeeded"
    after = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert after["stale"] == 0


async def test_historical_translation_without_config_is_unknown(client, pdf_path):
    """Rows written before provenance existed must be reported, not hidden."""
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    await wait_job(client, (await client.post("/v1/jobs", json={"documentId": doc_id})).json()["job"]["id"])

    app_state = client._transport.app.state.paperloom  # type: ignore[attr-defined]
    with app_state.db.connect() as conn:
        conn.execute(
            "UPDATE segments SET translation_config=NULL WHERE document_id=? AND translation IS NOT NULL",
            (doc_id,),
        )
    status = (await client.get(f"/v1/documents/{doc_id}/translation-status")).json()
    assert status["unknown"] == status["total"]
    assert status["stale"] == 0
    assert "unknown" in status["reasons"]
    assert status["needsAttention"] is True


async def test_reading_state_roundtrip(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.put(
        f"/v1/reading/{doc_id}",
        json={
            "page": 3,
            "mode": "dual",
            "sidebarWidth": 420,
            "selection": {"text": "sparse attention", "page": 2},
        },
    )
    assert response.status_code == 200
    state = response.json()["state"]
    assert state["page"] == 3
    assert state["sidebar_width"] == 420
    assert state["selection"]["text"] == "sparse attention"

    fetched = (await client.get(f"/v1/reading/{doc_id}")).json()["state"]
    assert fetched["mode"] == "dual"
    assert fetched["selection"]["page"] == 2


async def test_analyses_are_listed(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    response = await client.post(
        "/v1/analysis", json={"kind": "card", "documentIds": [doc_id]}
    )
    assert response.status_code == 200
    listed = await client.get("/v1/analyses", params={"documentId": doc_id})
    assert listed.status_code == 200
    analyses = listed.json()["analyses"]
    assert analyses
    assert analyses[0]["kind"] == "card"
    assert analyses[0]["result"]


async def test_translate_specific_pages_only(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    job_id = (
        await client.post("/v1/jobs", json={"documentId": doc_id, "pages": [1]})
    ).json()["job"]["id"]
    job = await wait_job(client, job_id)
    assert job["state"] == "succeeded"
    segments = (await client.get(f"/v1/documents/{doc_id}/segments")).json()["segments"]
    assert any(s.get("translation") for s in segments if s["page"] == 1)
    assert not any(s.get("translation") for s in segments if s["page"] > 1)


async def test_search_finds_segment(client, pdf_path):
    data = await register(client, pdf_path)
    response = await client.post(
        "/v1/search",
        json={"documentId": data["document"]["id"], "query": "LoomAttention"},
    )
    assert response.status_code == 200
    hits = response.json()["hits"]
    assert hits
    assert hits[0]["page"] >= 1


async def test_missing_document_returns_404(client):
    response = await client.get("/v1/documents/nope")
    assert response.status_code == 404
    response = await client.post("/v1/jobs", json={"documentId": "nope"})
    assert response.status_code == 404


async def test_register_rejects_bad_path(client, tmp_path):
    response = await client.post(
        "/v1/documents/register",
        json={
            "libraryId": "1",
            "itemKey": "A",
            "attachmentKey": "B",
            "pdfPath": str(tmp_path / "missing.pdf"),
        },
    )
    assert response.status_code == 400

    txt = tmp_path / "file.txt"
    txt.write_text("not a pdf")
    response = await client.post(
        "/v1/documents/register",
        json={
            "libraryId": "1",
            "itemKey": "A",
            "attachmentKey": "B",
            "pdfPath": str(txt),
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "kind", ["card", "experiment", "novelty", "compare", "outline"]
)
async def test_all_analysis_kinds(client, pdf_path, kind):
    data = await register(client, pdf_path)
    payload = {"kind": kind, "documentIds": [data["document"]["id"]]}
    if kind == "compare":
        payload["documentIds"] = [data["document"]["id"], data["document"]["id"]]
    response = await client.post("/v1/analysis", json=payload)
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "done"
