"""Schema migrations must survive being replayed on a database that already ran them.

Every other test starts from an empty file, so it only ever sees the "apply
everything once" path. Real users have a database that has been at some version
for months — and that is where a migration list can hurt them.

Two failures this guards against:

* a migration inserted in the *middle* of the list renumbers everything after it,
  so a database at the old version replays a script it has already run. This
  happened for real: the live service refused to start with
  ``duplicate column name: parser_version`` on a database that had been healthy.
* an ``ALTER TABLE ... ADD COLUMN`` that runs twice, which is not idempotent.

Both are checked against a real file rather than the in-memory assumption that
"current == version" is always right.
"""

from __future__ import annotations

import sqlite3

from paperloom_service.db import MIGRATIONS, Database


def _columns(path, table: str) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _version(path) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else 0


def test_a_fresh_database_gets_every_column(tmp_path):
    db = Database(tmp_path / "fresh.sqlite")
    db.migrate()
    assert "attachments" in _columns(db.path, "messages")
    assert "parser_version" in _columns(db.path, "documents")
    assert "layout" in _columns(db.path, "jobs")
    assert "translation_config" in _columns(db.path, "segments")
    assert _version(db.path) == len(MIGRATIONS)


def test_migrating_twice_changes_nothing(tmp_path):
    db = Database(tmp_path / "twice.sqlite")
    db.migrate()
    before = _columns(db.path, "messages")
    db.migrate()
    assert _columns(db.path, "messages") == before


def test_replaying_every_migration_does_not_fail(tmp_path):
    """The exact shape of the live failure: run them all again from zero."""
    db = Database(tmp_path / "replay.sqlite")
    db.migrate()
    with sqlite3.connect(db.path) as conn:
        conn.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    db.migrate()
    assert "attachments" in _columns(db.path, "messages")
    assert _version(db.path) == len(MIGRATIONS)


def test_a_database_one_version_behind_only_runs_the_new_step(tmp_path):
    db = Database(tmp_path / "behind.sqlite")
    db.migrate()
    with sqlite3.connect(db.path) as conn:
        conn.execute(
            "UPDATE meta SET value=? WHERE key='schema_version'",
            (str(len(MIGRATIONS) - 1),),
        )
        # Undo that last column so the step has real work to do.
        conn.execute("ALTER TABLE messages DROP COLUMN attachments")
    db.migrate()
    assert "attachments" in _columns(db.path, "messages")


def test_the_newest_migration_is_appended_not_inserted(tmp_path):
    """Cheap structural guard: the newest change must be the last entry.

    Without knowing history this can only check the *current* state, which is
    exactly what is needed — a contributor adding a migration in the middle is the
    mistake, and it shows up here as "the last entry is not the new one".
    """
    assert "attachments" in MIGRATIONS[-1]
