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
│    └─ /health         version + capability report                                   │
│  SQLite (WAL) + FTS5   documents, segments, translations, jobs, messages, terms      │
│  pdf/                  pdfminer.six extraction, paragraph merge, alignment           │
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
2. Lines are merged into paragraphs using vertical gap, indent and terminal
   punctuation heuristics; running headers/footers are removed.
3. Translations are produced per paragraph, so the mapping is exact at
   paragraph level (`segment.id`).
4. The UI shows the *measured* alignment level: `segment` (default) or `page`
   when a paragraph could not be merged reliably. BabelDOC output is a separate
   layout-preserving deliverable and is never used as the alignment source.

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

Re-parsing is versioned (`PARSER_VERSION`). When it runs, translations are
matched back by source text (`replace_segments(..., keep_translations=True)`),
so improving segmentation does not invalidate work the user already paid for.

## Trust boundary

Paper text is untrusted content. It is always placed in the user message inside
explicit delimiters and the system prompt states that document content must not
be treated as instructions. Citation markers returned by the model are
validated against the actual retrieved segment ids; unknown markers are
dropped and recorded in the message metadata.
