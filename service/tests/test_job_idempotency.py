"""A repeated translation request must not create a second job while one is in flight.

Two things reach the create endpoint twice in normal use: a double-click, and the
client's retry after a response was lost. Both used to translate — and bill — the
same pages again.

The guard only matters while a job is still queued or running; once it finished,
asking again is a normal request. The fake LLM finishes instantaneously, so these
tests drive the manager directly and compare inside a single tick, which is exactly
the double-click window.
"""

from __future__ import annotations

import pytest

from paperloom_service.config import RuntimeConfig, Settings
from paperloom_service.db import Database
from paperloom_service.jobs import JobManager


@pytest.fixture
def manager(cfg: RuntimeConfig) -> JobManager:
    db = Database(cfg.data_dir / "jobs.sqlite")
    db.migrate()
    return JobManager(db, cfg, lambda: Settings(), lambda: None)


DOC = "doc-1"


async def test_the_same_request_twice_returns_the_same_job(manager: JobManager):
    first = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    second = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    assert second["id"] == first["id"]


async def test_page_order_does_not_defeat_the_guard(manager: JobManager):
    first = manager.create_translation_job(DOC, pages=[1, 2], attach_existing=True)
    second = manager.create_translation_job(DOC, pages=[2, 1], attach_existing=True)
    assert second["id"] == first["id"]


async def test_whole_document_matches_only_whole_document(manager: JobManager):
    everything = manager.create_translation_job(DOC, pages=None, attach_existing=True)
    one_page = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    again = manager.create_translation_job(DOC, pages=None, attach_existing=True)
    assert one_page["id"] != everything["id"]
    assert again["id"] == everything["id"]


async def test_a_different_page_set_creates_its_own_job(manager: JobManager):
    """Translating page 5 while 1-3 runs is legitimate, not an accident."""
    first = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    other = manager.create_translation_job(DOC, pages=[2], attach_existing=True)
    assert other["id"] != first["id"]


async def test_a_different_document_is_untouched(manager: JobManager):
    first = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    other = manager.create_translation_job("doc-2", pages=[1], attach_existing=True)
    assert other["id"] != first["id"]


async def test_retry_still_creates_a_new_job(manager: JobManager):
    """`retry` must not be swallowed by the guard — that is the whole point of it."""
    first = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    forced = manager.create_translation_job(DOC, pages=[1], force=True, attach_existing=False)
    assert forced["id"] != first["id"]


async def test_a_finished_job_no_longer_blocks(manager: JobManager):
    first = manager.create_translation_job(DOC, pages=[1], attach_existing=True)
    manager.db.update_job(first["id"], state="succeeded")
    assert manager.find_duplicate(DOC, [1]) is None
