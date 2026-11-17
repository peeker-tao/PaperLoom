# Development

## Requirements

- Node.js 20+ (npm 10+)
- Python 3.10+ (3.12 recommended; BabelDOC requires 3.12)
- Zotero 7-10 for manual testing

## Install

```powershell
# service
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "service[dev]"

# plugin
cd plugin
npm.cmd install
```

> On Windows PowerShell the `npm` shim may be blocked by the execution policy.
> Use `npm.cmd` (as above) or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Checks

```powershell
.\scripts\check.ps1        # typecheck + lint + unit tests + plugin build
```

## Build the XPI

```powershell
.\scripts\build.ps1
# -> dist/paperloom-<version>.xpi
```

The XPI is a zip of `plugin/` with the built bundle in `plugin/content/`.
`manifest.json` must stay at the archive root.

## Load the plugin into Zotero without building

1. Close Zotero.
2. In the profile `extensions/` directory create a file named
   `paperloom@peeker.dev` whose content is the absolute path to `plugin/`.
3. Delete `extensions.lastAppBuildId` / `extensions.lastAppVersion` from
   `prefs.js` and restart Zotero.
4. Start Zotero with `-purgecaches -ZoteroDebugText`.

## Run the service manually

```powershell
python -m paperloom_service --port 23124 --data-dir .\data
```

Environment variables:

| Variable | Purpose |
| --- | --- |
| `PAPERLOOM_TOKEN` | override the generated instance token |
| `DEEPSEEK_API_KEY` | fall back to an env key when none is stored |
| `PAPERLOOM_DATA_DIR` | data directory |
| `PAPERLOOM_LOG_LEVEL` | `DEBUG`/`INFO`/`WARNING` |

## Tests

```powershell
python -m pytest service/tests -q
```

Tests use a fake DeepSeek transport (`PAPERLOOM_FAKE_LLM=1`) so they never call
the network. A real end-to-end smoke test is documented in
`docs/TESTING.md` and is opt-in.

## Repository layout

See `docs/ARCHITECTURE.md`. Each directory has a single responsibility:
`plugin/src/zotero` talks to Zotero APIs, `plugin/src/ui` renders, `plugin/src/service`
speaks HTTP; the service keeps `pdf/`, `deepseek.py`, `jobs.py` separate.
