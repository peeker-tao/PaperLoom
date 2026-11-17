"""Optional BabelDOC adapter.

BabelDOC / PDFMathTranslate-next are AGPL-3.0 and are NOT bundled with
PaperLoom. They are invoked as an external process and only when the user has
installed them. When missing, translation jobs still complete with
paragraph-level bilingual reading; only the layout-preserving PDF is absent.

Process handling rules (covered by ``tests/test_babeldoc.py``):

* one deadline for the whole run, including stdout draining;
* cancel, timeout and service shutdown kill the process **and its children**;
* the process is always awaited so it is reaped;
* the temporary config (which holds the API key) is deleted and its content is
  never logged;
* stdout is kept in a bounded ring buffer with the key redacted;
* produced PDFs are validated (header + page count) before being reported.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from ..urls import openai_sdk_base_url

log = logging.getLogger("paperloom.babeldoc")

MAX_LOG_LINES = 200
MAX_LINE_CHARS = 400
TERMINATE_GRACE = 5.0

# Anything that looks like a credential in engine output.
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)(\S+)"), r"\1***"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)(\S+)"), r"\1***"),
]


class BabeldocError(RuntimeError):
    """Base class with a stable ``code`` the API can surface."""

    code = "babeldoc_error"
    retryable = False

    def __init__(self, message: str, *, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class EngineMissing(BabeldocError):
    code = "engine_missing"

    def __init__(self) -> None:
        super().__init__(
            "未找到 BabelDOC。运行 `uv tool install --python 3.12 BabelDOC` 后重试，"
            "或在设置中填写可执行文件路径。"
        )


class EngineLaunchFailed(BabeldocError):
    code = "engine_launch_failed"
    retryable = True

    def __init__(self, detail: str) -> None:
        super().__init__(f"无法启动 BabelDOC：{detail}", detail=detail)


class EngineFailed(BabeldocError):
    code = "engine_failed"

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message, detail=detail)


class EngineTimeout(BabeldocError):
    code = "engine_timeout"
    retryable = True

    def __init__(self, seconds: float) -> None:
        super().__init__(f"BabelDOC 执行超时（{seconds:.0f} 秒），已终止进程")


class EngineCancelled(BabeldocError):
    code = "cancelled"


class EmptyArtifacts(BabeldocError):
    code = "empty_artifacts"
    retryable = True

    def __init__(self) -> None:
        super().__init__("BabelDOC 已结束，但没有生成任何 PDF 产物")


class InvalidArtifact(BabeldocError):
    code = "invalid_artifact"

    def __init__(self, reason: str) -> None:
        super().__init__(f"BabelDOC 产物无效：{reason}")


CANCELLED = EngineCancelled("任务已取消")


# --------------------------------------------------------------------------- #
# Engine discovery
# --------------------------------------------------------------------------- #

_engine_cache: dict | None = None


def find_engine() -> str | None:
    """Configured path, then PATH, then common install locations."""
    configured = os.environ.get("PAPERLOOM_BABELDOC_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured
    exe = shutil.which("babeldoc")
    if exe:
        return exe
    candidates = [
        Path.home() / ".local" / "bin" / "babeldoc.exe",
        Path.home() / ".local" / "bin" / "babeldoc",
        Path(os.environ.get("APPDATA", "")) / "Python" / "Scripts" / "babeldoc.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "uv"
        / "tools"
        / "babeldoc"
        / "Scripts"
        / "babeldoc.exe",
        Path(os.environ.get("APPDATA", ""))
        / "uv"
        / "tools"
        / "babeldoc"
        / "Scripts"
        / "babeldoc.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _probe_version(exe: str) -> str:
    """Best-effort ``babeldoc --version``; failures are not fatal."""
    try:
        import subprocess

        result = subprocess.run(
            [exe, "--version"], capture_output=True, timeout=20, check=False, text=True
        )
        lines = (result.stdout or result.stderr or "").strip().splitlines()
        return lines[-1][:60] if lines else ""
    except Exception:  # noqa: BLE001 - version probing must never break startup
        return ""


def engine_info(refresh: bool = False) -> dict:
    global _engine_cache
    if _engine_cache is not None and not refresh:
        return dict(_engine_cache)
    exe = find_engine()
    info = {
        "available": bool(exe),
        "path": exe or "",
        "version": _probe_version(exe) if exe else "",
        "license": "AGPL-3.0",
        "note": "" if exe else "未安装（可选）。安装后可按版式输出双语 PDF。",
    }
    _engine_cache = info
    return dict(info)


def reset_engine_cache() -> None:
    global _engine_cache
    _engine_cache = None


# --------------------------------------------------------------------------- #
# Redaction and process control
# --------------------------------------------------------------------------- #

def redact(text: str, secret: str = "") -> str:
    """Remove credentials from engine output before it reaches logs/UI."""
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "sk-***")
    for pattern, replacement in SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned[:MAX_LINE_CHARS]


async def _kill_tree(process: asyncio.subprocess.Process) -> None:
    """Terminate the process and its children, then reap it."""
    if process.returncode is not None:
        return
    try:
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(process.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=TERMINATE_GRACE)
            except asyncio.TimeoutError:  # pragma: no cover - taskkill hangs
                killer.kill()
        else:
            try:
                os.killpg(os.getpgid(process.pid), 9)
            except (ProcessLookupError, PermissionError):
                process.kill()
    except (FileNotFoundError, ProcessLookupError):  # pragma: no cover
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=TERMINATE_GRACE)
    except asyncio.TimeoutError:  # pragma: no cover
        log.warning("BabelDOC did not exit after kill")


def _validate_pdf(path: Path, *, expected_pages: int | None = None) -> int:
    """Return the page count, raising InvalidArtifact when the file is unusable."""
    try:
        with open(path, "rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise InvalidArtifact("文件头不是 %PDF-")
    except OSError as exc:
        raise InvalidArtifact(f"无法读取 {path.name}：{exc}") from exc
    try:
        from pypdf import PdfReader

        pages = len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise InvalidArtifact(f"无法解析 {path.name}：{exc}") from exc
    if pages <= 0:
        raise InvalidArtifact(f"{path.name} 没有页面")
    if expected_pages and pages > expected_pages * 3:
        raise InvalidArtifact(f"{path.name} 页数异常（{pages} 页）")
    return pages


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
        f"openai-base-url = {q(openai_sdk_base_url(base_url))}",
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
    except OSError:  # pragma: no cover - Windows ACLs
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
    cancel_token: asyncio.Event | None = None,
    on_progress=None,
    expected_pages: int | None = None,
) -> dict:
    """Run BabelDOC and return validated artifacts.

    ``output_dir`` must be unique per job: it is cleared first so stale output
    from an earlier attempt can never be reported as a new result.
    """
    exe = find_engine()
    if not exe:
        raise EngineMissing()
    source = Path(pdf_path)
    if not source.is_file():
        raise EngineFailed(f"输入 PDF 不存在：{source}")
    if source.stat().st_size == 0:
        raise EngineFailed("输入 PDF 为空文件")

    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
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
    argv = [exe, "--config", str(config_path), "--files", str(source)]
    ring: list[str] = []
    started = time.time()

    def remember(line: str) -> None:
        if not line:
            return
        ring.append(redact(line, api_key))
        if len(ring) > MAX_LOG_LINES:
            del ring[0 : len(ring) - MAX_LOG_LINES]

    process: asyncio.subprocess.Process | None = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(workdir),
            )
        except (OSError, ValueError) as exc:
            raise EngineLaunchFailed(str(exc)) from exc
        assert process.stdout is not None

        async def pump() -> None:
            assert process is not None and process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode("utf-8", "replace").strip()
                remember(line)
                if on_progress:
                    try:
                        await on_progress(redact(line, api_key))
                    except Exception:  # UI callback must not break the run
                        log.debug("babeldoc progress callback failed", exc_info=True)

        pump_task = asyncio.create_task(pump())
        # The deadline also covers stdout draining: a child that keeps the pipe
        # open is killed instead of blocking forever.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            if cancel_token and cancel_token.is_set():
                raise CANCELLED
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EngineTimeout(timeout)
            done, _ = await asyncio.wait({pump_task}, timeout=min(0.5, remaining))
            if pump_task in done:
                break
        code = await process.wait()
        if code != 0:
            raise EngineFailed(f"BabelDOC 退出码 {code}", detail="\n".join(ring[-12:]))
    finally:
        if process is not None and process.returncode is None:
            await _kill_tree(process)
        # The config holds the API key: delete it before anything else.
        try:
            config_path.unlink()
        except OSError:
            pass
        shutil.rmtree(workdir, ignore_errors=True)

    mono = sorted(output_dir.glob("*.mono.pdf"))
    dual = sorted(output_dir.glob("*.dual.pdf"))
    if not mono and not dual:
        raise EmptyArtifacts()
    result: dict = {"mono": None, "dual": None, "pages": {}, "output_dir": str(output_dir)}
    for kind, candidates in (("mono", mono), ("dual", dual)):
        if not candidates:
            continue
        path = candidates[0]
        # Guard against a stale file that survived the clear (e.g. locked file).
        if path.stat().st_mtime < started - 1:
            continue
        try:
            result["pages"][kind] = _validate_pdf(path, expected_pages=expected_pages)
        except InvalidArtifact:
            if kind == "dual" and result.get("mono"):
                log.warning("dual PDF invalid; keeping mono output only")
                continue
            raise
        result[kind] = str(path)
    if not result["mono"] and not result["dual"]:
        raise EmptyArtifacts()
    return result
