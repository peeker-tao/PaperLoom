# Changelog

All notable changes to PaperLoom are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
