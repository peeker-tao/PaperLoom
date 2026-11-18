"""Re-parsing must not throw away translations the user already paid for."""

from __future__ import annotations

from paperloom_service.db import Database


def make_db(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.migrate()
    db.upsert_document(
        {
            "id": "doc1",
            "library_id": 1,
            "item_key": "ABCD1234",
            "file_hash": "hash",
            "title": "Paper",
            "pages": 1,
            "pdf_path": str(tmp_path / "a.pdf"),
        }
    )
    return db


def segments(texts: list[str]) -> list[dict]:
    return [
        {
            "id": f"p1-s{i}",
            "page": 1,
            "ordinal": i,
            "text": text,
            "bbox": [0, 0, 100, 20],
            "kind": "body",
        }
        for i, text in enumerate(texts)
    ]


def test_reparse_keeps_translations_of_unchanged_text(tmp_path):
    db = make_db(tmp_path)
    first = segments(["Paragraph one.", "Paragraph two."])
    db.replace_segments("doc1", first)
    db.update_translation("doc1", "p1-s0", "第一段。")

    # The parser produced a new segmentation: ids shift, one text survives.
    second = segments(["Intro line.", "Paragraph one.", "Paragraph three."])
    reused = db.replace_segments("doc1", second)

    stored = {seg["text"]: seg for seg in db.get_segments("doc1")}
    assert reused == 1
    assert stored["Paragraph one."]["translation"] == "第一段。"
    assert stored["Intro line."]["translation"] is None
    # The paragraph that no longer exists is simply gone.
    assert "Paragraph two." not in stored


def test_reparse_can_discard_translations_on_request(tmp_path):
    db = make_db(tmp_path)
    db.replace_segments("doc1", segments(["Paragraph one."]))
    db.update_translation("doc1", "p1-s0", "第一段。")

    reused = db.replace_segments("doc1", segments(["Paragraph one."]), keep_translations=False)

    assert reused == 0
    assert db.get_segments("doc1")[0]["translation"] is None
