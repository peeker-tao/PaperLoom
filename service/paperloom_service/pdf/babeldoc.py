"""Optional BabelDOC adapter.

BabelDOC / PDFMathTranslate-next are AGPL-3.0 and are NOT bundled with
PaperLoom. They are invoked as an external process and only when the user has
installed them. When missing, translation jobs still complete with
paragraph-level bilingual reading; only the layout-preserving PDF is absent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger("paperloom.babeldoc")


class EngineMissing(RuntimeError):
    pass


def find_engine() -> str | None:
    exe = shutil.which("babeldoc")
    if exe:
        return exe
    # Common locations when installed with `uv tool install` / pip --user.
    candidates = [
        Path.home() / ".local" / "bin" / "babeldoc.exe",
        Path.home() / ".local" / "bin" / "babeldoc",
        Path(os.environ.get("APPDATA", "")) / "Python" / "Scripts" / "babeldoc.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def engine_info() -> dict:
    exe = find_engine()
    return {"available": bool(exe), "path": exe or "", "license": "AGPL-3.0"}


def _write_config(
    workdir: Path,
    *,
    api_key: str,
    base_url: str,
    model: str,
    lang_in: str,
    lang_out: str,
    qps: float,
    output_dir: Path,
    pages: str | None,
) -> Path:
    def q(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [
        "[babeldoc]",
        "openai = true",
        f"openai-model = {q(model)}",
        f"openai-base-url = {q(base_url.rstrip('/') + '/v1')}",
        f"openai-api-key = {q(api_key)}",
        f"lang-in = {q(lang_in)}",
        f"lang-out = {q(lang_out)}",
        f"qps = {qps}",
        f"output = {q(str(output_dir))}",
        "report-interval = 0.5",
    ]
    if pages:
        lines.append(f"pages = {q(pages)}")
    config_path = workdir / "babeldoc.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
    except OSError:  # pragma: no cover
        pass
    return config_path


async def translate_pdf(
    *,
    pdf_path: Path,
    output_dir: Path,
    api_key: str,
    base_url: str,
    model: str,
    pages: str | None = None,
    lang_in: str = "en",
    lang_out: str = "zh",
    qps: float = 4.0,
    timeout: float = 3600.0,
    on_progress=None,
) -> dict:
    """Run BabelDOC and return produced artifacts.

    The API key is passed through a 0600 temp config file instead of argv so it
    does not show up in process listings.
    """
    exe = find_engine()
    if not exe:
        raise EngineMissing(
            "未找到 BabelDOC。运行 `uv tool install --python 3.12 BabelDOC` 后重试，"
            "或将 BabelDOC 可执行文件加入 PATH。"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="paperloom-babeldoc-"))
    config_path = _write_config(
        workdir,
        api_key=api_key,
        base_url=base_url,
        model=model,
        lang_in=lang_in,
        lang_out=lang_out,
        qps=qps,
        output_dir=output_dir,
        pages=pages,
    )
    cmd = [exe, "--config", str(config_path), "--files", str(pdf_path)]
    log.info("starting BabelDOC: %s", " ".join(cmd[:2]))
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir),
        )
        assert process.stdout is not None
        last_lines: list[str] = []
        async for raw in process.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            last_lines.append(line)
            if len(last_lines) > 40:
                last_lines.pop(0)
            if on_progress:
                await on_progress(line)
        code = await asyncio.wait_for(process.wait(), timeout=timeout)
        if code != 0:
            tail = "\n".join(last_lines[-12:])
            raise RuntimeError(f"BabelDOC 退出码 {code}: {tail}")
    except asyncio.TimeoutError as exc:
        process.kill()
        raise TimeoutError("BabelDOC 翻译超时") from exc
    finally:
        # Remove the config file immediately: it contains the API key.
        try:
            config_path.unlink()
        except OSError:
            pass
        shutil.rmtree(workdir, ignore_errors=True)

    mono = sorted(output_dir.glob("*.mono.pdf"))
    dual = sorted(output_dir.glob("*.dual.pdf"))
    return {
        "mono": str(mono[0]) if mono else None,
        "dual": str(dual[0]) if dual else None,
        "output_dir": str(output_dir),
    }
