"""SQLite persistence layer with FTS5 search and forward-only migrations."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        library_id TEXT NOT NULL DEFAULT '',
        item_key TEXT NOT NULL DEFAULT '',
        attachment_key TEXT NOT NULL DEFAULT '',
        file_hash TEXT NOT NULL DEFAULT '',
        pdf_path TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        pages INTEGER NOT NULL DEFAULT 0,
        alignment TEXT NOT NULL DEFAULT 'none',
        alignment_note TEXT NOT NULL DEFAULT '',
        scanned INTEGER NOT NULL DEFAULT 0,
        text_chars INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS segments (
        id TEXT NOT NULL,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        page INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        text TEXT NOT NULL,
        translation TEXT,
        bbox TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'body',
        align TEXT NOT NULL DEFAULT 'exact',
        PRIMARY KEY (document_id, id)
    );
    CREATE INDEX IF NOT EXISTS idx_segments_doc ON segments(document_id, page, ordinal);

    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        state TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'queued',
        progress TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        usage TEXT,
        artifacts TEXT NOT NULL DEFAULT '[]',
        options TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_doc ON jobs(document_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS job_events (
        job_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        event TEXT NOT NULL,
        data TEXT NOT NULL,
        at REAL NOT NULL,
        PRIMARY KEY (job_id, seq)
    );

    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations TEXT NOT NULL DEFAULT '[]',
        model TEXT NOT NULL DEFAULT '',
        usage TEXT,
        status TEXT NOT NULL DEFAULT 'done',
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);

    CREATE TABLE IF NOT EXISTS terms (
        id TEXT PRIMARY KEY,
        document_id TEXT,
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT 'paper',
        status TEXT NOT NULL DEFAULT 'suggested',
        note TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_terms_unique
        ON terms(IFNULL(document_id, ''), lower(source));

    CREATE TABLE IF NOT EXISTS reading_state (
        document_id TEXT PRIMARY KEY,
        page INTEGER NOT NULL DEFAULT 1,
        mode TEXT NOT NULL DEFAULT 'dual',
        sidebar_width INTEGER NOT NULL DEFAULT 380,
        sidebar_open INTEGER NOT NULL DEFAULT 1,
        updated_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS analyses (
        id TEXT PRIMARY KEY,
        document_ids TEXT NOT NULL,
        kind TEXT NOT NULL,
        input TEXT NOT NULL DEFAULT '{}',
        result TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS translation_cache (
        key TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        created_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS segment_fts (
        segment_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        page INTEGER NOT NULL,
        text TEXT NOT NULL
    );
    """,
    """ALTER TABLE reading_state ADD COLUMN selection TEXT;""",
    # Which configuration produced a translation. NULL means the row predates
    # this column ("unknown" provenance); user data is preserved.
    """ALTER TABLE segments ADD COLUMN translation_config TEXT;""",
    # Layout (BabelDOC) status is tracked separately from text translation so a
    # failed/absent engine never hides the usable text result.
    """ALTER TABLE jobs ADD COLUMN layout TEXT;""",
]


def now() -> float:
    return time.time()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            row = conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            current = int(row["value"]) if row else 0
            for index, script in enumerate(MIGRATIONS, start=1):
                if index <= current:
                    continue
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(index),),
                )
            if not _fts5_available(conn):
                _create_fts_fallback(conn)

    # ------------------------------------------------------------------ #
    # Documents and segments
    # ------------------------------------------------------------------ #
    def upsert_document(self, doc: dict[str, Any]) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT file_hash FROM documents WHERE id=?", (doc["id"],)
            ).fetchone()
            if existing and existing["file_hash"] == doc.get("file_hash"):
                conn.execute(
                    "UPDATE documents SET title=?, pages=?, alignment=?, alignment_note=?, "
                    "scanned=?, text_chars=?, pdf_path=?, updated_at=? WHERE id=?",
                    (
                        doc.get("title", ""),
                        doc.get("pages", 0),
                        doc.get("alignment", "none"),
                        doc.get("alignment_note", ""),
                        1 if doc.get("scanned") else 0,
                        doc.get("text_chars", 0),
                        doc.get("pdf_path", ""),
                        now(),
                        doc["id"],
                    ),
                )
                return
            conn.execute(
                """INSERT INTO documents(
                    id, library_id, item_key, attachment_key, file_hash, pdf_path, title,
                    pages, alignment, alignment_note, scanned, text_chars, created_at, updated_at)
                   VALUES (:id, :library_id, :item_key, :attachment_key, :file_hash, :pdf_path,
                    :title, :pages, :alignment, :alignment_note, :scanned, :text_chars,
                    :created_at, :updated_at)
                   ON CONFLICT(id) DO UPDATE SET
                    library_id=excluded.library_id, item_key=excluded.item_key,
                    attachment_key=excluded.attachment_key, file_hash=excluded.file_hash,
                    pdf_path=excluded.pdf_path, title=excluded.title, pages=excluded.pages,
                    alignment=excluded.alignment, alignment_note=excluded.alignment_note,
                    scanned=excluded.scanned, text_chars=excluded.text_chars,
                    updated_at=excluded.updated_at
                """,
                {
                    "id": doc["id"],
                    "library_id": str(doc.get("library_id", "")),
                    "item_key": doc.get("item_key", ""),
                    "attachment_key": doc.get("attachment_key", ""),
                    "file_hash": doc.get("file_hash", ""),
                    "pdf_path": doc.get("pdf_path", ""),
                    "title": doc.get("title", ""),
                    "pages": int(doc.get("pages", 0)),
                    "alignment": doc.get("alignment", "none"),
                    "alignment_note": doc.get("alignment_note", ""),
                    "scanned": 1 if doc.get("scanned") else 0,
                    "text_chars": int(doc.get("text_chars", 0)),
                    "created_at": doc.get("created_at", now()),
                    "updated_at": now(),
                },
            )
            # A different file hash invalidates all derived data for this document.
            conn.execute("DELETE FROM segments WHERE document_id=?", (doc["id"],))
            conn.execute("DELETE FROM segment_fts WHERE document_id=?", (doc["id"],))

    def get_document(self, doc_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_documents(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def replace_segments(self, doc_id: str, segments: Iterable[dict]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM segments WHERE document_id=?", (doc_id,))
            conn.execute("DELETE FROM segment_fts WHERE document_id=?", (doc_id,))
            for seg in segments:
                conn.execute(
                    """INSERT INTO segments(id, document_id, page, ordinal, text, translation,
                        bbox, kind, align) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        seg["id"],
                        doc_id,
                        int(seg["page"]),
                        int(seg["ordinal"]),
                        seg["text"],
                        seg.get("translation"),
                        json.dumps(seg["bbox"]),
                        seg.get("kind", "body"),
                        seg.get("align", "exact"),
                    ),
                )
                conn.execute(
                    "INSERT INTO segment_fts(segment_id, document_id, page, text) VALUES (?,?,?,?)",
                    (seg["id"], doc_id, int(seg["page"]), seg["text"]),
                )

    def get_segments(self, doc_id: str, page: int | None = None) -> list[dict]:
        sql = (
            "SELECT s.*, d.title AS document_title FROM segments s "
            "JOIN documents d ON d.id=s.document_id WHERE s.document_id=?"
        )
        params: list[Any] = [doc_id]
        if page is not None:
            sql += " AND s.page=?"
            params.append(page)
        sql += " ORDER BY s.page, s.ordinal"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item["bbox"] = json.loads(item["bbox"])
                raw_config = item.get("translation_config")
                item["translationConfig"] = (
                    json.loads(raw_config) if raw_config else None
                )
                out.append(item)
            return out

    def get_segment(self, doc_id: str, segment_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM segments WHERE document_id=? AND id=?",
                (doc_id, segment_id),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["bbox"] = json.loads(item["bbox"])
            return item

    def update_translation(
        self, document_id: str, segment_id: str, translation: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE segments SET translation=? WHERE document_id=? AND id=?",
                (translation, document_id, segment_id),
            )

    def set_segment_done(
        self,
        document_id: str,
        segment_id: str,
        translation: str,
        config: dict | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE segments SET translation=?, translation_config=? "
                "WHERE id=? AND document_id=?",
                (
                    translation,
                    json.dumps(config, ensure_ascii=False) if config else None,
                    segment_id,
                    document_id,
                ),
            )

    def search(self, doc_id: str, query: str, limit: int = 8) -> list[dict]:
        q = _fts_query(query)
        if not q:
            return []
        with self.connect() as conn:
            try:
                rows = conn.execute(
                    """SELECT f.segment_id, f.page, snippet(segment_fts, 3, '[', ']', '…', 12) AS snippet
                       FROM segment_fts f WHERE f.document_id=? AND segment_fts MATCH ?
                       LIMIT ?""",
                    (doc_id, q, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = _like_search(conn, doc_id, query, limit)
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #
    def create_job(self, job: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO jobs(id, document_id, state, stage, progress, error, usage,
                    artifacts, options, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job["id"],
                    job["document_id"],
                    job["state"],
                    job.get("stage", "queued"),
                    json.dumps(job.get("progress", {})),
                    json.dumps(job["error"]) if job.get("error") else None,
                    json.dumps(job["usage"]) if job.get("usage") else None,
                    json.dumps(job.get("artifacts", [])),
                    json.dumps(job.get("options", {})),
                    job.get("created_at", now()),
                    now(),
                ),
            )

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "state",
            "stage",
            "progress",
            "error",
            "usage",
            "artifacts",
            "layout",
            "document_id",
        }
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"progress", "error", "usage", "artifacts", "layout"}:
                value = json.dumps(value) if value is not None else None
            sets.append(f"{key}=?")
            params.append(value)
        if not sets:
            return
        sets.append("updated_at=?")
        params.append(now())
        params.append(job_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", params)

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return _job_row(row) if row else None

    def list_jobs(self, doc_id: str | None = None, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            if doc_id:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE document_id=? ORDER BY created_at DESC LIMIT ?",
                    (doc_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [_job_row(r) for r in rows]

    def latest_unfinished_jobs(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE state IN ('queued','running') ORDER BY created_at"
            ).fetchall()
            return [_job_row(r) for r in rows]

    def append_event(self, job_id: str, seq: int, event: str, data: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO job_events(job_id, seq, event, data, at) VALUES (?,?,?,?,?)",
                (job_id, seq, event, json.dumps(data, ensure_ascii=False), now()),
            )

    def get_events(self, job_id: str, after: int = -1) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_events WHERE job_id=? AND seq>? ORDER BY seq",
                (job_id, after),
            ).fetchall()
            return [
                {
                    "seq": r["seq"],
                    "event": r["event"],
                    "data": json.loads(r["data"]),
                    "at": r["at"],
                }
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # Conversations
    # ------------------------------------------------------------------ #
    def ensure_conversation(self, conv_id: str, doc_id: str, title: str = "") -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE conversations SET updated_at=? WHERE id=?", (now(), conv_id)
                )
                return
            conn.execute(
                "INSERT INTO conversations(id, document_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conv_id, doc_id, title, now(), now()),
            )

    def add_message(self, msg: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO messages(id, document_id, conversation_id, role, content,
                    citations, model, usage, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    msg["id"],
                    msg["document_id"],
                    msg["conversation_id"],
                    msg["role"],
                    msg["content"],
                    json.dumps(msg.get("citations", [])),
                    msg.get("model", ""),
                    json.dumps(msg["usage"]) if msg.get("usage") else None,
                    msg.get("status", "done"),
                    msg.get("created_at", now()),
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now(), msg["conversation_id"]),
            )

    def list_conversations(self, doc_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE document_id=? ORDER BY updated_at DESC",
                (doc_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_messages(self, conversation_id: str, limit: int = 200) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item["citations"] = json.loads(item["citations"])
                item["usage"] = json.loads(item["usage"]) if item["usage"] else None
                out.append(item)
            return out

    # ------------------------------------------------------------------ #
    # Terms
    # ------------------------------------------------------------------ #
    def upsert_term(self, term: dict) -> dict:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM terms WHERE IFNULL(document_id,'')=? AND lower(source)=lower(?)",
                (term.get("document_id") or "", term["source"]),
            ).fetchone()
            term_id = existing["id"] if existing else term["id"]
            conn.execute(
                """INSERT INTO terms(id, document_id, source, target, scope, status, note, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET target=excluded.target, status=excluded.status,
                    note=excluded.note, updated_at=excluded.updated_at""",
                (
                    term_id,
                    term.get("document_id"),
                    term["source"],
                    term["target"],
                    term.get("scope", "paper"),
                    term.get("status", "suggested"),
                    term.get("note", ""),
                    now(),
                ),
            )
            row = conn.execute("SELECT * FROM terms WHERE id=?", (term_id,)).fetchone()
            return dict(row)

    def list_terms(self, doc_id: str | None = None) -> list[dict]:
        with self.connect() as conn:
            if doc_id:
                rows = conn.execute(
                    "SELECT * FROM terms WHERE document_id=? OR scope='global' ORDER BY scope, source",
                    (doc_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM terms ORDER BY scope, source"
                ).fetchall()
            return [dict(r) for r in rows]

    def delete_term(self, term_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM terms WHERE id=?", (term_id,))
            return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Reading state / analyses / cache
    # ------------------------------------------------------------------ #
    def get_reading_state(self, doc_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reading_state WHERE document_id=?", (doc_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("selection"):
                try:
                    data["selection"] = json.loads(data["selection"])
                except json.JSONDecodeError:
                    data["selection"] = None
            return data

    def save_reading_state(self, doc_id: str, **fields: Any) -> dict:
        current = self.get_reading_state(doc_id) or {
            "page": 1,
            "mode": "dual",
            "sidebar_width": 380,
            "sidebar_open": 1,
            "selection": None,
        }
        # ``selection`` may legitimately be None (clear it); other fields only
        # change when the client actually sent a value.
        allowed = {"page", "mode", "sidebar_width", "sidebar_open", "selection"}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if value is None and key != "selection":
                continue
            current[key] = value
        if current.get("mode") not in {"original", "translated", "dual"}:
            current["mode"] = "dual"
        current["page"] = max(1, int(current.get("page") or 1))
        current["sidebar_width"] = max(
            300, min(620, int(current.get("sidebar_width") or 380))
        )
        selection = current.get("selection")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO reading_state(
                       document_id, page, mode, sidebar_width, sidebar_open, selection, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(document_id) DO UPDATE SET page=excluded.page, mode=excluded.mode,
                    sidebar_width=excluded.sidebar_width, sidebar_open=excluded.sidebar_open,
                    selection=excluded.selection, updated_at=excluded.updated_at""",
                (
                    doc_id,
                    int(current["page"]),
                    current["mode"],
                    int(current["sidebar_width"]),
                    1 if current["sidebar_open"] else 0,
                    json.dumps(selection, ensure_ascii=False) if selection else None,
                    now(),
                ),
            )
        return self.get_reading_state(doc_id) or {}

    def save_analysis(self, analysis: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO analyses(id, document_ids, kind, input, result, model, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    analysis["id"],
                    json.dumps(analysis.get("document_ids", [])),
                    analysis["kind"],
                    json.dumps(analysis.get("input", {})),
                    analysis.get("result", ""),
                    analysis.get("model", ""),
                    now(),
                ),
            )

    def get_analysis(self, analysis_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM analyses WHERE id=?", (analysis_id,)
            ).fetchone()
            return _analysis_row(row) if row else None

    def list_analyses(self, doc_id: str, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM analyses ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            item = _analysis_row(row)
            if doc_id in item["documentIds"]:
                result.append(item)
            if len(result) >= limit:
                break
        return result

    def get_cached_translation(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT target FROM translation_cache WHERE key=?", (key,)
            ).fetchone()
            return row["target"] if row else None

    def put_cached_translation(
        self, key: str, model: str, source: str, target: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO translation_cache(key, model, source, target, created_at) VALUES (?,?,?,?,?)",
                (key, model, source, target, now()),
            )


def _job_row(row: sqlite3.Row) -> dict:
    job = dict(row)
    for key in ("progress", "error", "usage", "artifacts", "options", "layout"):
        job[key] = (
            json.loads(job[key])
            if job.get(key)
            else (None if key != "artifacts" else [])
        )
    job["id"] = job["id"]
    job["createdAt"] = job.pop("created_at")
    job["updatedAt"] = job.pop("updated_at")
    job["documentId"] = job.pop("document_id")
    return job


def _analysis_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["documentIds"] = json.loads(data.get("document_ids") or "[]")
    data["input"] = json.loads(data.get("input") or "{}")
    data["createdAt"] = data.pop("created_at")
    return data


def _fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _create_fts_fallback(
    conn: sqlite3.Connection,
) -> None:  # pragma: no cover - rare builds
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_fts_like ON segment_fts(document_id, text)"
    )


def _fts_query(query: str) -> str:
    terms = [t for t in _tokenize(query) if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in terms[:12])


def _tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", text)


def _like_search(conn: sqlite3.Connection, doc_id: str, query: str, limit: int):
    pattern = f"%{query}%"
    return conn.execute(
        "SELECT segment_id, page, text AS snippet FROM segment_fts "
        "WHERE document_id=? AND text LIKE ? LIMIT ?",
        (doc_id, pattern, limit),
    ).fetchall()
