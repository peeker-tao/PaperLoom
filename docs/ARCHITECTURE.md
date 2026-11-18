# PaperLoom Architecture

PaperLoom is split into three parts that talk over loopback HTTP only.

```
┌─────────────────────────── Zotero 10 (Firefox 140 ESR) ───────────────────────────┐
│  plugin/bootstrap.js                                                              │
│    ├─ lifecycle + window hooks                                                     │
│    ├─ reader sidebar (React, shadow DOM inside the reader iframe)                  │
│    ├─ selection popup actions / note writer / page jump                            │
│    └─ service client (fetch + SSE)  ─────────────────────────────┐                 │
└──────────────────────────────────────────────────────────────────┼─────────────────┘
                                                                   │ 127.0.0.1:<port>
                                                                   │ X-PaperLoom-Token
┌──────────────────────────── local service (Python) ───────────────▼─────────────────┐
│  FastAPI                                                                           │
│    ├─ /v1/jobs        translation jobs, progress, cancel, retry (SSE)               │
│    ├─ /v1/chat        contextual Q&A (SSE)                                          │
│    ├─ /v1/analysis    reading card / experiment / novelty / limitations / compare   │
│    ├─ /v1/glossary    paper-local + global terms                                     │
│    ├─ /v1/reading     reading state + conversation persistence                      │
│    ├─ /v1/documents/{id}/markdown  bilingual Markdown (English, then Chinese)         │
│    ├─ /v1/documents/{id}/page/{n}.png  page or region as PNG (figure crops)          │
│    └─ /health         version + capability report                                   │
│  SQLite (WAL) + FTS5   documents, segments, translations, jobs, messages, terms      │
│  pdf/                  pdfminer.six extraction, paragraph merge, alignment, render    │
│  deepseek.py           OpenAI-compatible client, retry/backoff, error mapping        │
│  babeldoc.py           optional external process (AGPL-3.0, user-installed)          │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼  https://api.deepseek.com
                                   DeepSeek API
```

## Why a local service

- PDF parsing, caching and long-running jobs are much cheaper outside the Zotero
  main thread; a crash in the parser cannot take Zotero down.
- The API key never leaves the machine except to DeepSeek. The plugin asks the
  service to perform calls; the key is stored in the service config.
- The service can be restarted, upgraded and diagnosed independently.

## Identity keys

Every artifact is keyed by `(libraryID, itemKey, attachmentKey, fileHash)`.

* `itemKey` is the parent regular item.
* `attachmentKey` distinguishes multiple PDF attachments of the same paper.
* `fileHash` (sha256 of the PDF) invalidates caches when the file is replaced.

## Alignment strategy

1. `pdfminer.six` extracts text lines with bounding boxes per page.
2. Lines are merged into paragraphs using vertical gap, indent, font size and
   terminal punctuation heuristics; running headers/footers are removed.
3. Translations are produced per paragraph, so the mapping is exact at
   paragraph level (`segment.id`).
4. The UI shows the *measured* alignment level: `segment` (default) or `page`
   when a paragraph could not be merged reliably. BabelDOC output is a separate
   layout-preserving deliverable and is never used as the alignment source.

### Three ways a paragraph gets cut, and how they are handled

pdfminer reports glyph runs, not paragraphs, so merging is where reading order
is decided. The failures seen on real papers:

| Symptom | Cause | Rule |
| --- | --- | --- |
| One line becomes two paragraphs, the second starting lowercase | pdfminer emits two objects for one visual line (`x 58.5–233.07` and `x 239.09–294.75`, both `y = 401.84`) | a line on the same baseline starting at or after the previous line's end is a `continuation` and is excluded from the column-edge measurement |
| Paragraph stops at the column break | a paragraph runs bottom-left → top-right, where the vertical gap is large | cross-column merge when both lines are body-size and the previous line ends with `-`, or ends mid-sentence and fills ≥ 86% of the column |
| A heading swallows the next paragraph | only the incoming line's font size was checked | both lines are compared against the body size |

### Three ways one paragraph gets cut in half, and how they are rejoined

Merging works line by line, so anything sitting *between* two halves of a
sentence separates them for good. A second pass (`_lift_inline_labels`,
`_join_broken_segments`) looks for the other half:

| Symptom | Cause | Signal |
| --- | --- | --- |
| `"…as self-supervision:"` / `[equation]` / `"where Percep denotes …"` | a display equation sits inside the sentence | search past `formula`/`table`/`figure`/`noise`/`meta`/`caption` for the owning paragraph; a trailing colon counts as unfinished |
| `"…results of E-RayZer"` / `"Datasets."` / `"trained on both …"` | a run-in label was laid out as its own block | short capitalised label with a full stop between an unfinished paragraph and a lowercase start |
| `"… of target views"` / `"(Itgt) to render …"` | the second half starts with a capital or a bracket, so "starts lowercase" misses it | a paragraph that stops at a function word (`… are conducted on`), after a comma, or past 120 chars without punctuation is unfinished |

`_join` also decides hyphenation: a trailing `-` at a line break never inserts a
space when the next fragment starts with a capital letter, so `E-` + `RayZer`
stays `E-RayZer` while `im-` + `plementing` is repaired with the document
vocabulary. The vocabulary cannot resolve every case — a fragment such as
`plementing` enters it simply by starting a line — so an unresolved hyphen is
kept rather than guessed away.


## Output format: Markdown, not a layout copy

The sidebar does not try to rebuild the PDF page. `markdown.py` turns the
segment list into ordinary Markdown — one block per paragraph, English first,
Chinese after, `##`/`###` derived from the section numbers — and every consumer
(sidebar, clipboard, Zotero note, `scripts/export_markdown.py`) renders that
same string. Reflowing text beats absolute positioning here: a sidebar is a
different width from a two-column paper, and text placed into boxes sized for
the original column shrinks until it is unreadable.

The page-accurate overlay (`plugin/src/ui/overlay.ts`, `版式` toggle) still
exists for figures and equations, where position carries meaning. It is a view
over the same segments, not a second pipeline.

## Figures are rendered by the service, not the plugin

The plugin cannot crop a PDF itself inside Zotero: the reader's pdf.js instance
is not reachable from the sidebar's iframe, and every attempt ended with
"图片需要回到 PDF 查看". So the service does it — `pdf/render.py` renders the page
with `pypdfium2` and cuts the region with `Pillow`:

```
GET /v1/documents/{id}/page/{n}.png?width=1400&bbox=x0,y0,x1,y1
  → 200 image/png, Cache-Control: private, max-age=3600
  → 400 bad_bbox | render_failed, 503 render_unavailable
```

`pdf/figures.py` decides the region, `PageCrop.tsx` fetches the PNG and turns it
into an object URL. `capabilities.render.available` reports whether
`pypdfium2` is installed; when it is not, the UI keeps the text fallback. The
plugin still has a client-side canvas path, used only if the service call fails.

Re-parsing is versioned (`PARSER_VERSION`, currently `8`). When it runs,
translations are matched back by source text
(`replace_segments(..., keep_translations=True)`), so improving segmentation
does not invalidate work the user already paid for. Expect few matches right
after a segmentation change: the paragraphs were merged, so their source text
differs.

## Trust boundary

Paper text is untrusted content. It is always placed in the user message inside
explicit delimiters and the system prompt states that document content must not
be treated as instructions. Citation markers returned by the model are
validated against the actual retrieved segment ids; unknown markers are
dropped and recorded in the message metadata.
