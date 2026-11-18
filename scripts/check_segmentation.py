"""Report segmentation quality for a PDF (paper-reading sanity check).

Usage:
    python scripts/check_segmentation.py path/to/paper.pdf [--pages 1-5]

Checks that paragraphs are real paragraphs, not single lines:

* share of segments that end with sentence punctuation;
* share of segments that start mid-sentence (previous segment did not end);
* leftover hyphenation ("exe-cuting"), stray glyph segments, leaked margin
  stamps (e.g. the arXiv identifier);
* median segment length in characters.
"""

from __future__ import annotations

import argparse
import itertools
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "service"))

from paperloom_service.pdf.extract import (
    PARSER_VERSION,
    _document_vocab,
    _drop_noise_lines,
    extract_lines,
    parse_pdf,
)

SENTENCE_END = tuple(".!?:。！？；;")
# A leaked margin stamp is a bare id/number/year, not a sentence starting with one.
STAMP_RE = re.compile(
    r"^(?:v\d+|\d{4}|\d{1,4}\s*[.,]?|\[cs\.[A-Z]{2}\]|arxiv:\s*\d{4}\.\d{4,5}v\d+)$",
    re.IGNORECASE,
)
HYPHEN_TOKEN_RE = re.compile(r"\b([A-Za-z]{2,})-([a-z]{2,})\b")
PROSE_KINDS = {"body", "abstract"}


def parse_range(spec: str) -> set[int] | None:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        elif part:
            pages.add(int(part))
    return pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--pages", default="", help="e.g. 1-3,7")
    args = parser.parse_args()

    path = Path(args.pdf)
    result = parse_pdf(path)
    # Vocabulary of the raw document, used to tell real hyphenation leftovers
    # ("exe-cuting") from legitimate compounds ("text-to-image").
    raw_lines, _ = extract_lines(path)
    VOCAB = _document_vocab(_drop_noise_lines(raw_lines))
    allowed = parse_range(args.pages)
    segments = [s for s in result["segments"] if not allowed or s["page"] in allowed]

    translatable = [
        s for s in segments if s["kind"] not in {"noise", "meta", "reference"}
    ]
    # Only real prose should look like a paragraph; headings, captions and
    # formulas legitimately do not end with a full stop.
    prose = [s for s in translatable if s["kind"] in PROSE_KINDS]
    lengths = [len(s["text"]) for s in prose]
    ended = [s for s in prose if s["text"].rstrip().endswith(SENTENCE_END)]

    # A prose segment that starts mid-sentence while its predecessor (also
    # prose) did not end one is a paragraph the merger failed to join.
    dangling = []
    by_page: dict[int, list[dict]] = {}
    for seg in segments:
        by_page.setdefault(seg["page"], []).append(seg)
    for page_segments in by_page.values():
        prose_segments = [s for s in page_segments if s["kind"] in PROSE_KINDS]
        for prev, cur in itertools.pairwise(prose_segments):
            if not prev["text"].rstrip().endswith(SENTENCE_END) and re.match(
                r"^[a-z(]", cur["text"]
            ):
                dangling.append((prev, cur))

    leftovers = [
        (seg["id"], m.group(0))
        for seg in translatable
        for m in HYPHEN_TOKEN_RE.finditer(seg["text"])
        # A real leftover is a hyphenated form that never occurs as such while
        # the glued form does appear: "exe-cuting" vs "executing".
        if m.group(0).lower() not in VOCAB
        and (m.group(1) + m.group(2)).lower() in VOCAB
    ]
    stamps = [s["id"] for s in segments if STAMP_RE.match(s["text"].strip())][:10]
    tiny = [s["id"] for s in prose if len(s["text"]) < 40]

    print(f"file            : {path.name}")
    print(f"parser version  : {PARSER_VERSION}")
    print(f"pages / segments: {result['pages']} / {len(segments)}")
    print(f"kinds           : {sorted({s['kind'] for s in segments})}")
    print(f"translatable    : {len(translatable)} (prose {len(prose)})")
    if lengths:
        print(
            f"prose length    : min={min(lengths)} median={int(statistics.median(lengths))} "
            f"max={max(lengths)} mean={int(statistics.mean(lengths))}"
        )
    ratio = len(ended) / max(1, len(prose))
    print(f"prose ends .,!? : {ratio:.0%} ({len(ended)}/{len(prose)})")
    print(f"dangling joins  : {len(dangling)}")
    print(f"leftover hyphens: {len(leftovers)} {leftovers[:6]}")
    print(f"margin stamps   : {stamps}")
    print(f"short prose     : {len(tiny)} {tiny[:8]}")

    # ~25% of prose paragraphs legitimately end mid-sentence: an interleaved
    # display equation or a page break splits them, and reordering text around
    # equations would break the visual correspondence with the PDF.
    ok = (
        ratio >= 0.75
        and len(dangling) <= len(prose) * 0.15
        and not stamps
        and not leftovers
    )
    print("\nRESULT:", "PASS" if ok else "NEEDS WORK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
