"""Plugin diagnostics: the service accepts log lines and records every request.

The sidebar runs inside the reader iframe, where ``Zotero.debug`` does not
exist, so a button that failed left no trace at all. These tests pin the two
halves of the replacement: the endpoint that accepts the lines, and the request
log that proves whether a call ever arrived.
"""

from __future__ import annotations

import logging


async def test_client_log_is_written_to_the_data_directory(client, cfg):
    response = await client.post(
        "/v1/client-log",
        json={"lines": ["first line", "second line"], "source": "plugin"},
    )
    assert response.status_code == 200
    assert response.json()["lines"] == 2

    log_file = cfg.data_dir / "logs" / "plugin.log"
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8").splitlines() == ["first line", "second line"]


async def test_client_log_requires_the_instance_token(client, cfg):
    response = await client.post(
        "/v1/client-log", json={"lines": ["nope"]}, headers={"x-paperloom-token": ""}
    )
    assert response.status_code == 401
    assert not (cfg.data_dir / "logs" / "plugin.log").exists()


async def test_client_log_caps_a_runaway_client(client, cfg):
    response = await client.post(
        "/v1/client-log", json={"lines": [f"line {i}" for i in range(500)]}
    )
    assert response.status_code == 200
    assert response.json()["lines"] == 200
    written = (cfg.data_dir / "logs" / "plugin.log").read_text(encoding="utf-8")
    assert len(written.splitlines()) == 200


async def test_requests_are_logged_so_a_missing_call_is_visible(client, caplog):
    """`GET /v1/status` must appear in the log; that is how "the button did
    nothing" gets distinguished from "the request never arrived"."""
    with caplog.at_level(logging.INFO, logger="paperloom.app"):
        await client.get("/v1/status")
    assert any(
        "GET /v1/status" in record.getMessage() for record in caplog.records
    ), [record.getMessage() for record in caplog.records]


async def test_rejected_token_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="paperloom.app"):
        await client.get("/v1/status", headers={"x-paperloom-token": "stale"})
    assert any("token mismatch" in record.getMessage() for record in caplog.records)
