# Changelog

All notable changes to PaperLoom are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.6] - 2026-11-18

### Added

- **"运行自检" in the settings panel.** It calls exactly what the buttons call
  and prints a pass/fail line for each: local service, instance token, API key,
  paper parsing, translation status, the chat stream (SSE), and page rendering.
  A feature that "does nothing" now says which step fails and why, instead of
  leaving the user to guess.
- Plugin diagnostics reach disk. The sidebar runs inside the reader iframe,
  where `Zotero.debug` does not exist — so `debug()` silently produced nothing
  and a failed click left no trace anywhere. Lines are now buffered (visible in
  设置) and shipped to `POST /v1/client-log`, which appends them to
  `<dataDir>/logs/plugin.log` with rotation.
- The service logs every request (`GET /v1/status -> 200 (7ms)`) and every
  rejected token. That is the only way to tell "the button did nothing" from
  "the request never arrived".

### Fixed

- 论文对比 no longer requires selecting papers in the Zotero main window: when
  nothing is selected it falls back to the papers already registered (each was
  parsed when it was opened once). The old behaviour — silently refusing with a
  one-line error — is what "对比用不了" looked like.
- The error banner has a close button. It used to stay on screen for the rest
  of the session after a single failure.
- Uncaught errors and unhandled rejections inside the reader iframe are recorded
  instead of disappearing.

### Verified

- 162 service tests (5 new for the log endpoint and request logging), 17 plugin
  tests, `ruff` clean. The self-test was exercised against the live service: all
  seven steps pass on a healthy install.

## [0.1.5] - 2026-11-18

### Added

- **Figures and tables are shown in the reading view.** A paper about image
  generation is unreadable without its pictures, and the Markdown view had
  silently dropped them. The service now finds the area each caption refers to
  (`figure` segments, `PARSER_VERSION` 6) and the plugin cuts that region out of
  the rendered page, so the reader sees the real picture — exact colours, axes,
  sub-labels — between the caption and the surrounding text.
- Region detection absorbs a table cell by cell instead of stopping at the first
  row, prefers the tighter of the two candidate sides (stacked tables used to
  steal each other's body), and refuses anything ambiguous: no text inside the
  region, no crop thinner than 55pt, none covering more than 80% of the page.

### Changed

- The reading view fills the sidebar. A centred 78-character column left a dead
  strip on both sides; long paragraphs also wrapped more than the width allowed.
- `SIDEBAR_MAX_WIDTH` is 960px instead of 620px, in the CSS and in the drag
  clamp, so a wide screen can actually be used for reading.

### Fixed

- Prose that merely mentions a table ("Table 1 shows results of …") was typed as
  a caption and printed at caption size. A caption now needs a separator right
  after the label.
- `97/96 段已译`: the two numbers were counted over different sets (references
  keep translations). Both are now counted over the same segments, and pictures
  are excluded.

### Verified

- 157 service tests (up from 150, including 7 for figure regions) and 17 plugin
  tests (including `pageRect` mapping). On the 21-page sample paper 10 of 13
  captions get a crop; every one was rendered to PNG and inspected.

## [0.1.4] - 2026-11-18

### Changed

- **The sidebar now shows a reading view instead of a layout replica.** Every
  paragraph is printed as the English original followed by the Chinese
  translation, in normal document flow. Re-creating the PDF layout inside a
  narrow sidebar was fragile (text had to be squeezed into boxes designed for a
  different column width) and it is not how anyone reads. The page-accurate view
  is still available behind the `版式` toggle.
- Markdown is the single output format: the sidebar, `复制 Markdown` and
  `存为笔记` all use the same server-side renderer, so what is exported is
  exactly what was read.

### Added

- `paperloom_service/markdown.py` and `GET /v1/documents/{id}/markdown`:
  renders a translated paper as Markdown — H1 is the paper's own title,
  `##`/`###` come from section numbers, paragraphs are English / blank line /
  Chinese, `<!-- pN -->` marks page boundaries, references are optional.
- Sidebar: copy the Markdown to the clipboard, or save it as a Zotero note
  attached to the item (saving again overwrites the same note instead of
  piling up duplicates).
- `scripts/export_markdown.py`: export a registered paper to a `.md` file from
  the command line.
- Translations survive re-parsing: when the parser version changes (or
  `重新解析` is used) translations are matched back by their source text, so a
  free segmentation improvement no longer destroys paid translations. The
  response reports how many were kept (`keptTranslations`).

### Fixed

- Author affiliations above the abstract (`2 Zhipu AI`, `1 Tsinghua
  University`) matched the section-number pattern and appeared as fake chapters.
  Short segments before the abstract on page 1 are now `meta`.
- The H1 was the Zotero attachment title (`Zheng 等 - 2024 - CogView3`)
  followed by the real title. The paper's own title is used, once.
- Figure captions and equation fragments that start with a number
  (`1024 (bottom). All prompts …`, `0 + σtϵ, t, ctext)`) were headings. Section
  headings now require a small section number followed by a capitalised word,
  and bibliographic-looking text never qualifies.
- Reference entries (`1. Achiam, J., …`) are classified as `reference` even
  when they look like numbered headings.

### Verified

- 150 service tests (up from 136) and 13 plugin tests; a live job on a 21-page
  paper: 99/99 segments, 37.7k characters of Markdown, 4 030 English words,
  6 045 Chinese characters, 18 headings — all of them real section headings.

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

- `scripts/check_segmentation.py` (paragraph/merge quality report),
  `scripts/check_translation_quality.py` (runs a real job and prints
  source/translation pairs with quality flags), `scripts/preview_overlay_png.py`
  (renders the bilingual view to a PNG offline) and `scripts/overlay_layout.py`
  (the shared text-fitting rules).

### Fixed (bilingual overlay rendering)

- **A cross-page paragraph produced a page-sized box.** Merging a paragraph that
  continues onto the next page mixed the coordinates of both pages, so the box
  covered the whole sheet and the opaque panel painted over figures and every
  other paragraph. The text is still joined (one complete sentence), but the box
  now stays on the page holding most of it, and any box taller than 70% of the
  page is rejected as a safety net.
- Overlay panels are opaque. At 93% opacity the English showed through and the
  page looked like it had doubled text.
- The translation is now fitted to its box: the largest font size at which the
  whole paragraph fits is chosen (down to 5px), instead of a fixed size that
  clipped the tail of long paragraphs. If nothing fits, the overlay is skipped
  rather than showing a truncated sentence.
- Lines are wrapped with the same rules as the offline preview: Latin words and
  numbers are never split (`C / ogView3`), and closing punctuation never starts
  a line (CJK typesetting rule).
- Text is top-aligned to the paragraph start instead of floating in the middle
  of the box.

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
