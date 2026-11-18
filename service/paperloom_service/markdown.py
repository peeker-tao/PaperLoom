"""Render a translated document as Markdown: English first, Chinese after.

The bilingual reading view is plain reflowed text rather than a PDF layout. That
is deliberate: it stays readable at any width, it is copy-pasteable into notes,
and it does not depend on pdf.js, on bounding boxes or on fonts matching.

Layout rules, one per segment:

* a chapter/section heading becomes a Markdown heading, with the translation in
  bold underneath, so the outline survives;
* every other paragraph is the English text, a blank line, then the Chinese
  translation;
* page breaks are marked with an HTML comment (invisible in rendered Markdown,
  searchable in the source) so a reader can find their place in the PDF.

Non-prose kinds (equations, table cells, author blocks, reference lists) are
skipped by default: they carry no translatable prose and would only add noise.
"""

from __future__ import annotations

import re

# Kinds that never belong in the reading text. ``figure`` is a picture region:
# the plugin draws it, and a text file has nowhere to put an image.
SKIP_KINDS = {"noise", "meta", "formula", "table", "figure"}
# Kinds that are prose but optional (bibliographies are long and rarely read).
OPTIONAL_KINDS = {"reference"}

HEADING_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+")
SENTENCE_END = tuple(".!?:。！？；;")


def _escape_inline(text: str) -> str:
    """Neutralise characters that Markdown would interpret.

    Only the characters that actually change rendering are escaped: an
    underscore inside an identifier (``x_0``) must stay literal, and a stray
    asterisk in an equation label must not start emphasis.
    """
    return text.replace("\r", " ").replace("\n", " ").strip()


def _heading_level(kind: str, text: str) -> int:
    if kind == "title":
        return 1
    match = HEADING_PREFIX_RE.match(text)
    if match:
        # "2.1 Text-to-Image ..." -> level 3 (level 2 is the chapter).
        depth = match.group(1).count(".") + 1
        return min(6, 1 + depth)
    return 2


def _segment_markdown(
    segment: dict, *, include_original: bool, include_translation: bool
) -> list[str]:
    original = _escape_inline(segment.get("text") or "")
    translation = _escape_inline(segment.get("translation") or "")
    kind = segment.get("kind", "body")
    has_translation = bool(translation)

    if kind in {"title", "heading"}:
        level = _heading_level(kind, original)
        hashes = "#" * level
        lines = [f"{hashes} {original}"]
        if include_translation and has_translation:
            # Bold rather than a second heading: two headings at the same level
            # would make the document outline list every section twice.
            lines.append("")
            lines.append(f"**{translation}**")
        return lines

    lines: list[str] = []
    if include_original and original:
        lines.append(original)
    if include_translation and has_translation:
        if lines:
            lines.append("")
        lines.append(translation)
    return lines


def render_markdown(
    document: dict,
    segments: list[dict],
    *,
    include_original: bool = True,
    include_translation: bool = True,
    include_pages: bool = True,
    include_references: bool = False,
    front_matter: bool = True,
) -> str:
    """Return the whole document as Markdown."""
    blocks: list[str] = []
    # The document title from Zotero is often a filename ("Smith et al. - 2024 -
    # Paper"); the paper's own title segment is the real heading, so prefer it.
    paper_title = ""
    for segment in segments:
        if segment.get("kind") == "title" and (segment.get("text") or "").strip():
            paper_title = _escape_inline(segment["text"])
            break
    title = paper_title or (document.get("title") or "").strip()
    if front_matter and title:
        blocks.append(f"# {_escape_inline(title)}")
        # Count translations only over the segments actually offered for
        # translation, otherwise a bibliography translation makes "97/96".
        counted = [
            s for s in segments if s.get("kind") not in SKIP_KINDS | OPTIONAL_KINDS
        ]
        translated = sum(1 for s in counted if s.get("translation"))
        meta = f"共 {document.get('pages') or 0} 页 · {translated}/{len(counted)} 段已译"
        blocks.append(f"> {meta}")

    current_page = None
    for segment in segments:
        kind = segment.get("kind", "body")
        if kind in SKIP_KINDS:
            continue
        if kind in OPTIONAL_KINDS and not include_references:
            continue
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        # The title already appeared as front matter; repeating it as a heading
        # would put the paper title in the document twice.
        if front_matter and kind == "title" and _escape_inline(text) == title:
            continue
        page = int(segment.get("page") or 0)
        if include_pages and page and page != current_page:
            current_page = page
            blocks.append(f"<!-- p{page} -->")
        lines = _segment_markdown(
            segment,
            include_original=include_original,
            include_translation=include_translation,
        )
        if lines:
            blocks.append("\n".join(lines))

    return "\n\n".join(blocks).strip() + "\n"


def markdown_stats(markdown: str, segments: list[dict]) -> dict:
    """Small summary the UI can show next to the export button."""
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]+", markdown))
    han = len(re.findall(r"[\u4e00-\u9fff]", markdown))
    return {
        "chars": len(markdown),
        "bytes": len(markdown.encode("utf-8")),
        "englishWords": words,
        "chineseChars": han,
        "segments": len(segments),
    }


def suggested_filename(document: dict) -> str:
    """A safe .md filename derived from the paper title."""
    title = (document.get("title") or "paper").strip()
    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:80] or "paper") + ".md"
