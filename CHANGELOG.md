# Changelog

All notable changes to PaperLoom are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-19

Reading view gets both fixes it needed: every paragraph is a complete sentence,
and figures are actually drawn inside Zotero.

### Fixed

- **一段话被切成两三段.** pdfminer occasionally emits two objects for one
  visual line. On page 2 of E-RayZer it produced
  `E-RayZer operates directly in 3D space,` (x 58.5–233.07) and
  `learning self-` (x 239.09–294.75) — both at `y = 401.84` — which became two
  separate paragraphs, the second starting with a lowercase word. A line on the
  same baseline whose start is at or after the previous line's end is now
  treated as the rest of that line (`continuation`), and is excluded from the
  column-edge measurement that decides paragraph ends.
- **段落跨栏被截断.** A paragraph that ran from the bottom of the left column
  to the top of the right column (`…We highlight key conclusions` at y 78.85,
  then `and summarize our contributions as follows:` at y 707.89) was never
  joined. Cross-column merges are now allowed when both lines are body-size and
  either the previous line ends with a hyphen or it ends with an open sentence
  and fills at least 86% of the column width.
- **算式把句子劈成两段.** `"…as self-supervision:"` / `[equation]` /
  `"where Percep denotes …"` used to become two paragraphs, so the second one
  was translated as a fragment that starts with a lowercase word. A continuation
  is now looked for past the interrupting block; a colon counts as an opening
  tail because it is what introduces a display equation.
- **小节标签插在句子中间.** `"…results of E-RayZer"` / `"Datasets."` /
  `"trained on both …"` — a run-in label laid out as its own block between the
  two halves of a sentence. The label is lifted out of the flow and the sentence
  rejoined, which fixes the case where the second half started lowercase.
- **句子被打断后另一半以大写开头.** When an equation or a picture sits inside a
  sentence, the rest often starts with a capital or a bracket
  (`"… of target views"` / `"(Itgt) to render …"`), so the "starts lowercase"
  test alone missed it. A paragraph that stops at a function word
  (`… are conducted on`), after a comma, or after more than 120 characters
  without punctuation is now recognised as unfinished.
- **`E-RayZer` 变成 `E- RayZer`.** The joiner inserted a space after any
  trailing hyphen. A hyphen at a line break now never adds a space when the next
  fragment starts with a capital letter, so compound names survive while
  hyphenation is still repaired.
- **正文被判成表格单元后整段消失.** `_looks_like_table_cell` treated any short
  line containing a digit as table furniture, so
  `supervised 3D reconstruction. Concretely, E-RayZer pre-` was classified
  `table` and hidden. Cells are now rejected when they contain punctuation
  *between* words followed by lowercase, or when they carry more than six
  tokens; `pre-` counts as a word when the digit rule is applied.
- **`(cid:N)` 残片被当成正文.** pdfminer prints glyphs it cannot map as
  `(cid:1)`, and those runs became one-line paragraphs
  (`tgt )(cid:1).`, `ψ ), and rendering (f rend`). They are now typed as
  formulas, as are short bracket-riddled runs with no sentence punctuation.
- **表格列头混进正文.** `Self-supervised?`, `Percep. Encoder [7]`,
  `Pose-sup. Baseline` were shown as paragraphs. A short line with no ordinary
  lowercase word is now a table cell even when it contains an abbreviation.
- **标题吞掉下一段.** Merging checked only the incoming line's font size, so
  `1. Introduction` (12 pt) absorbed `Pre-training with self-supervision…`
  (10 pt). Both sides are now measured against the body size.
- **跨栏合并后的框覆盖整页.** The overlay rectangle of a merged cross-column
  block was the union of both columns. It is now anchored to the column that
  holds most of the text.
- **图片显示不了.** Figures were cropped in the plugin with pdf.js, which does
  not work inside Zotero's reader iframe, so every figure fell back to
  "图片需要回到 PDF 查看". Cropping moved to the service: `pypdfium2` renders the
  page and `Pillow` cuts the region.

Measured on E-RayZer (17 pages, 444 segments), before → after:

| Metric | Before | After |
| --- | --- | --- |
| Prose segments | 130 | **86** |
| Median prose length | 245 chars | **337 chars** |
| Paragraphs starting lowercase | 28 | **2** |
| Paragraphs not ending a sentence | 35 | **9** |

The two remaining lowercase starts and most of the nine are reading-order
defects (a figure or a table column extracted out of order), not merge failures.

### Added

- `GET /v1/documents/{document_id}/page/{page}.png?width=&bbox=` — renders a
  page (or a crop of it) as PNG, `Cache-Control: private, max-age=3600`.
  Returns 400 `bad_bbox` / `render_failed`, 503 `render_unavailable` when
  `pypdfium2` is missing.
- `capabilities.render.available`, surfaced in the 自检 panel as
  **页面渲染（图片裁切）**.
- `service/paperloom_service/pdf/render.py` (`render_available`,
  `render_page_png`, `parse_bbox`).
- 10 layout tests (`tests/test_layout.py`) built from the real coordinates
  above, and 6 rendering tests (`tests/test_render.py`) that skip when
  `pypdfium2` / `Pillow` are absent. They also pin the equation split, the
  run-in label and the `(cid:N)` debris.

### Changed

- `PARSER_VERSION` is now `8`. Re-parsing keeps existing translations by
  matching source text, so bumping it no longer discards your work. Expect fewer
  reused translations after this one — paragraphs were merged, so their source
  text changed.
- New service dependencies: `pypdfium2`, `pillow`.

## [0.1.9] - 2026-11-18

### Fixed

- **Controls off-screen in a narrow reader pane.** The sidebar used a fixed
  `min-width: 300px` and the saved width as-is, so when the reader pane was
  narrower than the saved width its left edge went past the viewport — the
  leftmost controls (tabs, the first items in a row) simply could not be
  clicked. The width is now clamped to `min(var(--pl-width), 100vw)` and the
  reading layer uses the same clamp, so the two never disagree.
- **`--pl-width` never reached the sidebar.** The variable was set on `<body>`,
  but the host element is a child of `<html>` and custom properties only inherit
  downwards: `var(--pl-width, 380px)` silently fell back to 380px, so the saved
  width did nothing and the reading layer's right offset stopped matching the
  sidebar. It is now set on `<html>` and `<body>` both.
- Every control re-declares `pointer-events: auto`. `.pl-root` is
  `pointer-events: none` so empty space still forwards clicks to the PDF, and
  nothing underneath an element with `pointer-events: none` is hit-testable
  unless it opts back in — a wrapper change could otherwise leave buttons
  visible but dead.

### Added

- **全部按钮可点击** self-test step. It hit-tests the centre of every control in
  the sidebar (descending into shadow roots) and names the element that
  intercepted it, e.g. `双语 被 DIV#cover-test 遮挡`. Verified by injecting a
  transparent covering layer: all 14 controls were reported, then cleared when
  the layer was removed.

## [0.1.8] - 2026-11-18

### Fixed

- **A transparent layer could cover the sidebar.** `.pl-sidebar` had
  `z-index: auto` while the reading layer had `z-index: 6`, so wherever the two
  overlapped the reading view painted on top — the fields below it looked
  covered by invisible glass and could not be clicked. The sidebar is now
  explicitly above it, and the composer sits in its own layer inside the sidebar.
- The host element is appended to `<html>` instead of `<body>`, and carries its
  hit-testing properties inline (`position`, `inset`, `pointer-events`,
  `z-index: 2147483647`). If Zotero's reader puts a stacking context or a
  higher-specificity rule on `<body>`, a large `z-index` inside it would be
  confined to that context and could still be covered by a sibling.
- Clicking a text field now focuses the field itself, not just the reader
  iframe: `iframeWindow.focus()` makes the document eligible for keys but does
  not move the caret into the input.

### Added

- `ui/probe.ts` and two new self-test steps — **输入框可点击** and **阅读器键盘焦点**.
  The first walks `elementFromPoint` down through shadow roots and names the
  element that actually receives the pointer, so "有一层东西挡住" becomes a
  concrete element name instead of a guess. The second reports whether the
  reader document owns the keyboard.

## [0.1.7] - 2026-11-18

### Fixed

- **The question box could not be typed into inside Zotero.** The textarea's
  value came straight from the shared store, so every keystroke depended on the
  store echoing the new text back. When that round trip did not return — which
  is what happens in the reader iframe — React restored the value it last saw
  and the box behaved like it was read-only. The draft is now owned locally and
  mirrored into the store, so typing sticks whether or not the echo arrives, and
  the send button is driven by the same local value. Verified by deliberately
  breaking the echo in the harness: text still types, Enter still sends.
- Text fields explicitly take keyboard focus from the reader iframe
  (`-moz-user-focus: normal`, plus a capture-phase `pointerdown` on the sidebar
  that calls `iframeWindow.focus()`). In Zotero the sidebar lives inside that
  iframe; if the main window keeps focus, clicks land but keys go to the item
  list instead.
- The first click and the first keystroke in the sidebar are logged once each.
  Together with the service request log this answers the only question that
  matters when a button "does nothing": did the event arrive at all?

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
