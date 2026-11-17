from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from paperloom_service.app import create_app
from paperloom_service.config import RuntimeConfig
from tests.fixtures import paper_pdf

TOKEN = "test-token"
HEADERS = {"x-paperloom-token": TOKEN}


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setenv("PAPERLOOM_FAKE_LLM", "1")


@pytest.fixture
def cfg(tmp_path) -> RuntimeConfig:
    config = RuntimeConfig(data_dir=tmp_path / "data", token=TOKEN)
    config.ensure_dirs()
    return config


@pytest.fixture
async def client(cfg) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(cfg)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://paperloom.test",
            headers=HEADERS,
            timeout=30,
        ) as http:
            yield http


@pytest.fixture
def pdf_path(tmp_path):
    return paper_pdf(tmp_path / "paper.pdf", pages=2)


async def register(client: httpx.AsyncClient, pdf_path) -> dict:
    response = await client.post(
        "/v1/documents/register",
        json={
            "libraryId": "1",
            "itemKey": "ITEM1234",
            "attachmentKey": "ATTACH12",
            "pdfPath": str(pdf_path),
            "title": "Synthetic Paper",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def wait_job(
    client: httpx.AsyncClient, job_id: str, timeout: float = 15.0
) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()["job"]
        if job["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {job}")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name = None
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif not line.strip() and name is not None:
            if data_lines:
                events.append((name, json.loads("\n".join(data_lines))))
            name, data_lines = None, []
    if name is not None and data_lines:
        events.append((name, json.loads("\n".join(data_lines))))
    return events
