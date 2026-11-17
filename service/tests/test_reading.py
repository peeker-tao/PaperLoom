"""Reading-state persistence: merge semantics, validation and isolation."""

from __future__ import annotations

from tests.conftest import register
from tests.fixtures import paper_pdf


async def test_reading_state_defaults(client, pdf_path):
    data = await register(client, pdf_path)
    body = (await client.get(f"/v1/reading/{data['document']['id']}")).json()
    assert body["state"] == {}


async def test_reading_state_merges_partial_patches(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]

    first = await client.put(f"/v1/reading/{doc_id}", json={"page": 2})
    assert first.status_code == 200
    second = await client.put(f"/v1/reading/{doc_id}", json={"mode": "original"})
    state = second.json()["state"]
    # The later patch must not reset the earlier page.
    assert state["page"] == 2
    assert state["mode"] == "original"


async def test_reading_state_clears_selection(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    selection = {"text": "some sentence", "page": 2, "rects": []}

    body = (await client.put(f"/v1/reading/{doc_id}", json={"selection": selection})).json()
    assert body["state"]["selection"]["text"] == "some sentence"

    cleared = (await client.put(f"/v1/reading/{doc_id}", json={"selection": None})).json()
    assert cleared["state"]["selection"] is None

    # Omitting the field keeps the stored value untouched.
    again = (await client.put(f"/v1/reading/{doc_id}", json={"selection": selection})).json()
    assert again["state"]["selection"]["text"] == "some sentence"
    kept = (await client.put(f"/v1/reading/{doc_id}", json={"page": 1})).json()
    assert kept["state"]["selection"]["text"] == "some sentence"


async def test_reading_state_rejects_invalid_values(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]

    assert (await client.put(f"/v1/reading/{doc_id}", json={"page": 0})).status_code == 422
    assert (await client.put(f"/v1/reading/{doc_id}", json={"page": -3})).status_code == 422
    assert (
        await client.put(f"/v1/reading/{doc_id}", json={"sidebarWidth": 10})
    ).status_code == 422
    assert (
        await client.put(f"/v1/reading/{doc_id}", json={"mode": "nonsense"})
    ).status_code == 422


async def test_reading_state_clamps_width(client, pdf_path):
    data = await register(client, pdf_path)
    doc_id = data["document"]["id"]
    body = (await client.put(f"/v1/reading/{doc_id}", json={"sidebarWidth": 200})).json()
    assert body["state"]["sidebar_width"] == 300
    body = (await client.put(f"/v1/reading/{doc_id}", json={"sidebarWidth": 1000})).json()
    assert body["state"]["sidebar_width"] == 620


async def test_reading_state_is_per_document(client, tmp_path):
    first = await register(client, paper_pdf(tmp_path / "a.pdf", pages=2))
    second = await register(
        client, paper_pdf(tmp_path / "b.pdf", pages=3, title="A Second Synthetic Paper")
    )
    first_id, second_id = first["document"]["id"], second["document"]["id"]
    assert first_id != second_id

    await client.put(f"/v1/reading/{first_id}", json={"page": 2, "mode": "dual"})
    await client.put(f"/v1/reading/{second_id}", json={"page": 3, "mode": "original"})

    state_first = (await client.get(f"/v1/reading/{first_id}")).json()["state"]
    state_second = (await client.get(f"/v1/reading/{second_id}")).json()["state"]
    assert (state_first["page"], state_first["mode"]) == (2, "dual")
    assert (state_second["page"], state_second["mode"]) == (3, "original")


async def test_reading_state_unknown_document(client):
    response = await client.put("/v1/reading/does-not-exist", json={"page": 1})
    assert response.status_code == 404
