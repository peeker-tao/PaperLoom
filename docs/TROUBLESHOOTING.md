# Troubleshooting

## The service does not start

1. Open **Tools → PaperLoom Settings → Service → Show diagnostics**.
2. The sidebar already shows the reason: the plugin runs the candidate
   interpreter itself, requires Python 3.10+, and on failure calls
   `python -m paperloom_service --check` to surface the real cause (for example
   `No module named paperloom_service`).
3. Check the service log at `%APPDATA%\PaperLoom\logs\service.log`.
4. Verify Python:
   ```powershell
   python --version
   python -c "import fastapi, pydantic, pdfminer; print('ok')"
   python -m paperloom_service --check
   ```
5. Start the service manually to see the error:
   ```powershell
   cd service
   python -m paperloom_service --port 23124
   ```

### "No module named paperloom_service"

The interpreter found on PATH is not the one with the dependencies. Either run
`scripts\install_service.ps1` (creates `.venv` and installs the service) or set
`extensions.paperloom.pythonPath` to `.venv\Scripts\python.exe`.

### The Store alias opens the Microsoft Store

`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` is a stub, not an
interpreter. PaperLoom skips `WindowsApps` directories and validates every
candidate by running it, so this alias is never launched.

### Port already in use

PaperLoom probes ports 23124-23140 and remembers the chosen port in
`%APPDATA%\PaperLoom\service.json`. If another program occupies the port, the
probe moves on automatically. A stale `service.json` is detected by the
`/health` version check and rewritten.

### Token mismatch (HTTP 401)

The instance token lives in `%APPDATA%\PaperLoom\token`. Deleting it while the
service runs causes 401s: stop the service and let the plugin regenerate it.

## DeepSeek errors

| Symptom | Meaning | Action |
| --- | --- | --- |
| `401` / `AuthenticationError` | key invalid or revoked | re-enter the key in settings |
| `402` / `Insufficient Balance` | account balance exhausted | top up |
| `429` / `RateLimit` | request rate too high | lower concurrency/QPS |
| `context_length_exceeded` | selection + context too large | switch context scope to "selection" |
| stream ends with `finish_reason=length` | output truncated | raise max output tokens |

All retries use exponential backoff with jitter and are capped (default 3).
Cancelling a request aborts the HTTP stream; retries are not performed for
user-cancelled requests.

## Translation produces empty or identical text

- `deepseek-flash` runs in *thinking* mode by default. PaperLoom explicitly
  disables thinking for translation requests. If you typed a custom model name,
  make sure it supports `chat/completions` with `thinking: {"type": "disabled"}`.
- Very short paragraphs (< 5 chars) are skipped by design.
- If the whole PDF has almost no extractable text, it is probably a scanned
  document: the job fails with `scanned_pdf` and suggests OCR.

## Bilingual view says "alignment: page"

Paragraph merging failed for that page (common with two-column layouts or
equation-heavy pages). The UI still lets you jump to the page, but the
paragraph-level highlight is unavailable. Install BabelDOC for a
layout-preserving PDF, or translate page ranges separately.

## The layout (overlay) view falls back to plain text

The overlay view renders the real page bitmap and anchors translations to their
original boxes. It falls back to the text columns when:

- the page is **rotated** — a plain scale + y-flip cannot reproduce pdf.js's
  rotation matrix, so the overlay would land on the wrong text;
- pdf.js does not finish rendering within 8 seconds (the task is cancelled
  instead of leaving the view hanging);
- `PDFViewerApplication.pdfDocument` is not ready yet — switch pages and back,
  or reopen the reader.

The underlying translations are unaffected: the text layout always works.

The footer also shows the layout PDF status independently of the translation:
`无排版引擎` means BabelDOC is not installed (optional, AGPL-3.0),
`排版PDF失败` means it ran and failed (the message is in the tooltip).

## Zotero does not show the sidebar

- Confirm the plugin version in **Tools → Add-ons** matches `manifest.json`.
- Open **Help → Debug Output Logging → View Output** and look for
  `PaperLoom:` lines.
- Zotero 10 changed several internal APIs; PaperLoom targets
  `strict_max_version: 10.0.*`. On a newer major version the plugin is disabled
  until updated.
