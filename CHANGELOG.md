# Changelog

All notable changes to PaperLoom are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-11-17

### Fixed

- **Translation quality: paragraphs are now real paragraphs.** Three defects
  combined to make every translation a fragment:
  - rotated margin stamps (the arXiv/Elsevier download marker) were never
    filtered, because the rotation lives on each glyph's matrix while the code
    checked the text line's matrix — which is empty. The stamp's single
    characters were emitted one per line, interleaved between body lines, so
    they both broke paragraph merging and got glued onto sentence ends
    ("… in terms of computational 1").
  - paragraph continuation was compared against the *first* line of the group,
    so the next paragraph's indented first line was accepted as a continuation
    and paragraphs merged into one another.
  - end-of-line hyphens were always removed, turning `text-` + `to-image` into
    `textto-image` and destroying the very terms these papers are about. They
    are now resolved with the document's own vocabulary (and compound
    continuations such as `state-of-the-` are recognised), with a second repair
    pass over the merged text.
- Display type (titles, section headings) is merged on size and spacing instead
  of left-edge alignment, so a wrapped title is one segment instead of two
  fragments ("CogView3: Finer and Faster Text-to-Image" + "Generation via
  Relay Diffusion" previously translated as a garbled half-sentence).
- Reference lists, display equations, table cells and figure labels are no
  longer sent to the translator: a `References` heading switches the section to
  `reference`, `=`-style fragments become `formula`, and runs of terse cells
  become `table`. This removes garbage output and most of the wasted tokens.
- Segmentation changes are versioned (`PARSER_VERSION`); a document parsed by an
  older version is rebuilt transparently and the sidebar says so.

### Changed

- Translation prompt rewritten for completeness, term consistency, academic
  register, and for reconstructing words broken across lines. Each batch now
  receives the paper title and the previous paragraph as read-only context.
- Model output is validated (`too_short` / `no_chinese` / `untranslated` /
  `truncated`) and retried per segment, so a lazy or truncated answer no longer
  replaces a paragraph with a two-word "translation".
- `is_translatable()` is the single rule shared by the job pipeline and the
  translation-status endpoint; fragments shorter than 12 characters are skipped.
- Prompt version bumped to 3, so existing translations are reported as outdated
  and can be refreshed with one click.

### Added

- `scripts/check_segmentation.py` (paragraph/merge quality report) and
  `scripts/check_translation_quality.py` (runs a real job and prints
  source/translation pairs with quality flags).

## [0.1.2] - 2026-11-17

### Added

- Image-preserving bilingual view: the real PDF page is rendered with the
  reader's pdf.js instance and translated paragraphs are placed on their
  original bounding boxes, so figures, formulas, tables and layout survive.
  Dual mode shows original and translated pages side by side (stacked in narrow
  sidebars); clicking a paragraph jumps to and highlights it in the PDF.
- Translation status is tracked per generation (model / base URL / prompt
  version / glossary / output limit / document hash); stale translations are
  reported and can be re-translated by an explicit action.
- Layout status is tracked separately from text translation
  (`succeeded` / `failed` / `missing` / `skipped`) and shown in the sidebar.
- `GET /v1/documents/{id}/translation-status` and `babeldoc_timeout` setting.
- `scripts/verify_live.py`, `scripts/check_overlay.py` and
  `scripts/preview_overlay.py` for live-API and overlay verification.
- Plugin unit tests for the overlay geometry, wired into CI.

### Changed

- Base URL handling is centralized: the chat endpoint, the OpenAI-compatible
  `/v1` base used by BabelDOC and the status message now agree, and pasted
  endpoint URLs are normalized instead of producing `/v1/v1`.
- Reading state writes accumulate instead of overwriting, are serialized to
  prevent stale writes, survive sidebar teardown, and are validated on restore.
- Python discovery runs each candidate interpreter, requires 3.10+ and skips the
  Microsoft Store alias; a failed start now reports the service's own `--check`
  output instead of a bare timeout.

### Fixed

- BabelDOC subprocess: one deadline covering output draining, process-tree kill
  on timeout/cancel/shutdown, per-job output directory, artifact validation,
  key redaction in logs and deletion of the temporary config file.
- Uppercase `[[SEG:…]]` citation markers bypassed validation and leaked into
  answers.
- Author/affiliation lines and single-character fragments were sent for
  translation; they are now classified as `meta` / `noise`.
- `selection` could never be cleared, and invalid page/sidebar values were
  accepted by the reading-state endpoint.

## [0.1.1] - 2026-11-17

### Added

- Figure/formula annotation questions can send the captured image to
  `deepseek-flash` (vision) as a Data URL; falls back to captions and nearby
  text with an explicit note when Zotero exposes no image data.
- Translation artifacts (BabelDOC mono/dual PDF) are verified (`%PDF-` header)
  and imported as Zotero child attachments; duplicates are skipped.
- Per-conversation model selector, token/cost display, glossary injection into
  Q&A prompts, page-range translation input, and "save whole conversation" notes.
- Reading state now persists the current selection, and the last analysis is
  restored when reopening a paper.

### Changed

- Service version and `/v1/status` report `llm=live|fake` for honest demo mode.
- Narrow reader windows collapse the bilingual view to a single column.

## [0.1.0] - 2026-11-17

### Added

- Repository skeleton: plugin/service split, JSON schemas, CI workflows, docs.
- Zotero plugin (TypeScript + React, esbuild) with `bootstrap.js` lifecycle,
  reader sidebar, selection popup actions, note creation and page jump.
- Local FastAPI service with SQLite storage, FTS5 search, instance-token auth,
  SSE streaming, DeepSeek client with retry/backoff and cancel support.
- PDF paragraph extraction and paragraph-level alignment between source and
  translation; scanned-PDF detection.
- Translation job pipeline with caching, progress, cancellation and resume.
- Contextual chat (selection / section / whole paper) with citation markers.
- Glossary management (paper-local and global).
- Research analysis templates: reading card, experiment, novelty, limitations,
  comparison, presentation outline.
- Reading state and conversation persistence keyed by library/item/attachment
  and file hash.
- Windows packaging scripts and release workflow producing XPI + service zip.

### Known limitations

- BabelDOC/pdf2zh-next is optional and must be installed separately (AGPL-3.0);
  layout-preserving PDF output is unavailable until it is installed.
- Paragraph alignment is text-block level, not glyph level. Cross-column
  paragraphs may be merged; the UI reports the actual alignment quality.
- Image-internal text is not re-rendered (figure images are kept as-is).
- Real DeepSeek calls were not exercised in CI or in the development environment
  (no API key); the protocol is covered by a fake LLM transport.
- Interactive UI flows in Zotero require manual acceptance; plugin startup and
  registration were verified on Zotero 10.0.8.
