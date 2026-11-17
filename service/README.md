# PaperLoom Service

Local FastAPI service used by the PaperLoom Zotero plugin. It never listens on a
public interface: the default bind address is `127.0.0.1` and every request must
carry the instance token from `%APPDATA%\PaperLoom\token`.

## Run

```powershell
python -m paperloom_service --port 23124
python -m paperloom_service --print-token
python -m paperloom_service --check
```

## Layout

| Module | Responsibility |
| --- | --- |
| `app.py` | HTTP/SSE routes, auth middleware, settings |
| `jobs.py` | background jobs, persisted events, cancel/retry/recover |
| `translate.py` | paragraph batching, cache, artifacts |
| `pdf/extract.py` | pdfminer extraction, paragraph merge, two-column order |
| `pdf/babeldoc.py` | optional external BabelDOC process (AGPL-3.0) |
| `deepseek.py` | OpenAI-compatible client with retry/backoff |
| `context.py` | context scopes and citation validation |
| `analysis.py` | research analysis prompt templates |
| `db.py` | SQLite schema + FTS5 |

## Tests

```powershell
python -m pytest tests -q
```

Tests force `PAPERLOOM_FAKE_LLM=1`, so no network calls and no API key are
needed.
