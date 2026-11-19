"""Settings connection test: it must test the values on screen, and not save them.

The bug: the endpoint accepted only a model, so a Base URL or key the user had
just typed was ignored — the UI reported success for a configuration that had
never been tried. Two properties matter as much as "it works":

  * nothing about the test is persisted (the key is used once and discarded);
  * a key can never come back out of the service, including in an error message.
"""

from __future__ import annotations

import pytest

from paperloom_service.app import redact_secrets


async def test_test_connection_uses_the_typed_base_url(client):
    """The typed URL must be the one reported back, not the saved one."""
    saved = (await client.get("/v1/settings")).json()["settings"]["base_url"]
    typed = "https://gateway.example.test/openai/v1"
    body = (await client.post("/v1/settings/test", json={"baseUrl": typed})).json()
    assert body["ok"] is True
    assert body["baseUrl"].startswith("https://gateway.example.test")
    assert body["baseUrl"] != saved
    # ...and the saved setting is untouched: testing is not saving.
    assert (await client.get("/v1/settings")).json()["settings"]["base_url"] == saved


async def test_test_connection_rejects_a_malformed_base_url(client):
    response = await client.post("/v1/settings/test", json={"baseUrl": "ftp://example.com"})
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "bad_base_url"
    assert "协议" in body["error"]["message"]


async def test_test_connection_reports_the_saved_key_path(client):
    """A blank key means "use the saved one" — the UI says exactly that."""
    body = (await client.post("/v1/settings/test", json={})).json()
    assert body["ok"] is True
    assert body["usedTypedKey"] is False
    assert body["model"]


async def test_test_connection_flags_a_typed_key_without_saving_it(client):
    before = (await client.get("/v1/settings")).json()["apiKey"]
    body = (
        await client.post("/v1/settings/test", json={"apiKey": "sk-typed-not-saved-000"})
    ).json()
    # The fake LLM accepts any key, so this succeeds — but it must say it used the
    # typed one, and the stored key must be untouched afterwards.
    assert body["ok"] is True
    assert body["usedTypedKey"] is True
    after = (await client.get("/v1/settings")).json()["apiKey"]
    assert after["configured"] == before["configured"]
    assert after.get("hint") == before.get("hint")


async def test_test_connection_rejects_an_unknown_model(client):
    body = (await client.post("/v1/settings/test", json={"model": "not-a-model"})).json()
    assert body["ok"] is False


async def test_the_typed_key_never_appears_in_the_response(client):
    # Deliberately not shaped like a real key, so the repo secret scan stays useful.
    secret = "sk-fake-key-for-tests-only"
    response = await client.post("/v1/settings/test", json={"apiKey": secret})
    assert secret not in response.text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Authorization: Bearer sk-fake-key-for-tests", "Authorization: Bearer ***"),
        ("x-api-key: sk-fake-key-for-tests", "x-api-key: ***"),
        ("bad key sk-fake-key-for-tests rejected", "bad key sk-*** rejected"),
        ("no secrets here", "no secrets here"),
    ],
)
def test_redact_secrets(raw, expected):
    assert redact_secrets(raw) == expected
