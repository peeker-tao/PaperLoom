"""Package the plugin XPI, the Windows service zip and updates.json."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
DIST = ROOT / "dist"

PLUGIN_FILES = [
    "manifest.json",
    "bootstrap.js",
    "prefs.js",
    "prefs.xhtml",
    "prefs.css",
    "icons/icon.png",
    "icons/icon@2x.png",
    "content/plugin.js",
    "content/prefs.js",
]

SERVICE_EXCLUDES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "data",
    "paperloom_service.egg-info",
    "build",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_plugin(version: str) -> Path:
    missing = [name for name in PLUGIN_FILES if not (PLUGIN / name).exists()]
    if missing:
        raise SystemExit(f"missing plugin files: {missing}. Run npm run build first.")
    target = DIST / f"paperloom-{version}.xpi"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in PLUGIN_FILES:
            archive.write(PLUGIN / name, name)
    return target


def build_service(version: str) -> Path:
    target = DIST / f"paperloom-service-{version}.zip"
    items = [
        PLUGIN.parent / "service" / "paperloom_service",
        PLUGIN.parent / "service" / "README.md",
    ]
    items.append(PLUGIN.parent / "service" / "pyproject.toml")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in items:
            if not item.exists():
                continue
            if item.is_file():
                archive.write(item, f"{item.parent.name}/{item.name}")
            else:
                for path in sorted(item.rglob("*")):
                    if path.is_dir() or any(
                        part in SERVICE_EXCLUDES for part in path.parts
                    ):
                        continue
                    if path.suffix in {".pyc", ".pyo"}:
                        continue
                    relative = path.relative_to(ROOT)
                    archive.write(path, str(relative).replace("\\", "/"))
        install = ROOT / "scripts" / "install_service.ps1"
        if install.exists():
            archive.write(install, "scripts/install_service.ps1")
    return target


def write_updates(version: str, xpi: Path) -> Path:
    update_url = f"https://github.com/peeker-tao/PaperLoom/releases/download/v{version}/paperloom-{version}.xpi"
    payload = {
        "addons": {
            "paperloom@peeker.dev": {
                "updates": [
                    {
                        "version": version,
                        "update_link": update_url,
                        "update_hash": f"sha256:{sha256(xpi)}",
                        "applications": {
                            "zotero": {
                                "strict_min_version": "7.0",
                                "strict_max_version": "10.0.*",
                            }
                        },
                    }
                ]
            }
        }
    }
    target = DIST / "updates.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return target


def main() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    plugin_manifest_version = json.loads(
        (PLUGIN / "package.json").read_text(encoding="utf-8")
    )["version"]
    service_version_file = ROOT / "service" / "paperloom_service" / "__init__.py"
    if plugin_manifest_version != version:
        print(f"warning: package.json {plugin_manifest_version} != manifest {version}")
    if f'__version__ = "{version}"' not in service_version_file.read_text(
        encoding="utf-8"
    ):
        print("warning: service __version__ differs from plugin version")

    DIST.mkdir(exist_ok=True)
    xpi = build_plugin(version)
    service = build_service(version)
    updates = write_updates(version, xpi)
    print(f"plugin  : {xpi}  ({xpi.stat().st_size} bytes)")
    print(f"service : {service}  ({service.stat().st_size} bytes)")
    print(f"updates : {updates}")


if __name__ == "__main__":
    main()
