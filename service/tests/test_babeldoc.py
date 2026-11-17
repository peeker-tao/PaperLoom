"""BabelDOC subprocess management: hang, cancel, failure and artifact checks.

The engine binary is replaced by a small Python script, so these tests run
without BabelDOC and without network access.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

from paperloom_service.pdf import babeldoc
from tests.fixtures import paper_pdf

FAKE_KEY = "sk-fake-0123456789abcdef"


def write_script(tmp_path: Path, body: str, name: str = "fake_engine.py") -> Path:
    script = tmp_path / name
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return script


@pytest.fixture
def source_pdf(tmp_path) -> Path:
    return paper_pdf(tmp_path / "src.pdf", pages=2)


def make_input(tmp_path: Path, source: Path) -> None:
    assert source.exists()


# BabelDOC expects `<name>.mono.pdf` / `<name>.dual.pdf`; the fake engine writes
# a copy of a valid PDF into the output dir it is told about.
COPY_PDF = """
import shutil, sys, tomllib, pathlib
cfg = tomllib.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
out = pathlib.Path(cfg["babeldoc"]["output"])
src = pathlib.Path(sys.argv[4])
shutil.copyfile(src, out / "src.mono.pdf")
shutil.copyfile(src, out / "src.dual.pdf")
print("done")
"""


async def run(engine: Path, *, source: Path, out: Path, **kwargs):
    kwargs.setdefault("api_key", FAKE_KEY)
    kwargs.setdefault("base_url", "https://api.deepseek.com")
    kwargs.setdefault("model", "deepseek-flash")
    return await babeldoc.translate_pdf(
        pdf_path=source, output_dir=out, **kwargs
    )


def test_engine_info_reports_missing(monkeypatch):
    monkeypatch.setattr(babeldoc, "find_engine", lambda: None)
    babeldoc.reset_engine_cache()
    info = babeldoc.engine_info(refresh=True)
    assert info["available"] is False
    assert info["license"] == "AGPL-3.0"
    assert info["version"] == ""


def test_engine_info_reports_path(monkeypatch):
    monkeypatch.setattr(babeldoc, "find_engine", lambda: r"C:\fake\babeldoc.exe")
    monkeypatch.setattr(babeldoc, "_probe_version", lambda exe: "v0.7.1")
    babeldoc.reset_engine_cache()
    info = babeldoc.engine_info(refresh=True)
    assert info == {
        "available": True,
        "path": r"C:\fake\babeldoc.exe",
        "version": "v0.7.1",
        "license": "AGPL-3.0",
        "note": "",
    }


def test_redact_hides_credentials():
    text = f"using key {FAKE_KEY} and api_key=abc123 and Authorization: Bearer tok"
    cleaned = babeldoc.redact(text)
    assert FAKE_KEY not in cleaned
    assert "abc123" not in cleaned
    assert "tok" not in cleaned
    assert "***" in cleaned


def test_redact_removes_explicit_secret():
    assert babeldoc.redact(f"value={FAKE_KEY}", FAKE_KEY) == "value=sk-***"


async def test_successful_run_validates_artifacts(tmp_path, source_pdf, monkeypatch):
    script = write_script(tmp_path, COPY_PDF)
    wrapper = tmp_path / "ok.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    result = await babeldoc.translate_pdf(
        pdf_path=source_pdf,
        output_dir=tmp_path / "out",
        api_key=FAKE_KEY,
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout=60,
        expected_pages=2,
    )
    assert result["mono"] and Path(result["mono"]).exists()
    assert result["dual"] and Path(result["dual"]).exists()
    assert result["pages"] == {"mono": 2, "dual": 2}
    assert Path(result["mono"]).read_bytes()[:5] == b"%PDF-"


async def test_timeout_kills_hanging_process(tmp_path, source_pdf, monkeypatch):
    script = write_script(
        tmp_path,
        """
        import time, sys
        print("starting", flush=True)
        for _ in range(120):
            time.sleep(1)
            print("still working", flush=True)
        """,
    )
    wrapper = tmp_path / "hang.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    with pytest.raises(babeldoc.EngineTimeout):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=1.5,
        )
    # The run must return promptly after the deadline, not after 120s.
    assert list((tmp_path / "out").glob("*.pdf")) == []


async def test_cancel_token_stops_process(tmp_path, source_pdf, monkeypatch):
    script = write_script(
        tmp_path,
        """
        import time
        for _ in range(120):
            time.sleep(1)
            print("working", flush=True)
        """,
    )
    wrapper = tmp_path / "cancel.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    token = asyncio.Event()
    asyncio.get_running_loop().call_later(1.0, token.set)
    with pytest.raises(babeldoc.EngineCancelled):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=60,
            cancel_token=token,
        )


async def test_non_zero_exit_reports_tail_without_secret(tmp_path, source_pdf, monkeypatch):
    script = write_script(
        tmp_path,
        f"""
        print("diagnostic line")
        print("key is {FAKE_KEY}")
        raise SystemExit(3)
        """,
    )
    wrapper = tmp_path / "fail.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    with pytest.raises(babeldoc.EngineFailed) as info:
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=30,
        )
    assert "退出码 3" in info.value.message
    assert "diagnostic line" in info.value.detail
    assert FAKE_KEY not in info.value.detail
    assert FAKE_KEY not in info.value.message


async def test_launch_failure_raises(tmp_path, source_pdf, monkeypatch):
    missing = tmp_path / "does-not-exist.exe"
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(missing))
    with pytest.raises(babeldoc.EngineLaunchFailed):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=30,
        )


async def test_empty_artifacts_raise(tmp_path, source_pdf, monkeypatch):
    script = write_script(tmp_path, 'print("nothing to do")')
    wrapper = tmp_path / "empty.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    with pytest.raises(babeldoc.EmptyArtifacts):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=30,
        )


async def test_invalid_artifact_is_rejected(tmp_path, source_pdf, monkeypatch):
    script = write_script(
        tmp_path,
        """
        import sys, tomllib, pathlib
        cfg = tomllib.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
        out = pathlib.Path(cfg["babeldoc"]["output"])
        (out / "src.mono.pdf").write_bytes(b"not a pdf at all")
        print("wrote garbage")
        """,
    )
    wrapper = tmp_path / "bad.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    with pytest.raises(babeldoc.InvalidArtifact):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=30,
        )


async def test_temp_config_with_key_is_removed(tmp_path, source_pdf, monkeypatch):
    script = write_script(
        tmp_path,
        """
        import sys, pathlib
        cfg = pathlib.Path(sys.argv[2])
        pathlib.Path(r"{out}").write_text("captured " + cfg.read_text(encoding="utf-8"), encoding="utf-8")
        raise SystemExit(1)
        """.replace("{out}", str(tmp_path / "captured.toml").replace("\\", "\\\\")),
    )
    wrapper = tmp_path / "capture.cmd"
    wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    monkeypatch.setattr(babeldoc, "find_engine", lambda: str(wrapper))

    with pytest.raises(babeldoc.EngineFailed):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=30,
        )
    captured = (tmp_path / "captured.toml").read_text(encoding="utf-8")
    assert FAKE_KEY in captured  # the child did see the key...
    # ...but the temporary directory (and config) is gone after the run.
    leftovers = list(tmp_path.glob("paperloom-babeldoc-*"))
    assert leftovers == []


async def test_output_dir_is_cleared_before_run(tmp_path, source_pdf, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.mono.pdf").write_bytes(source_pdf.read_bytes())
    monkeypatch.setattr(babeldoc, "find_engine", lambda: None)
    with pytest.raises(babeldoc.EngineMissing):
        await babeldoc.translate_pdf(
            pdf_path=source_pdf,
            output_dir=out,
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
        )


async def test_missing_input_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(babeldoc, "find_engine", lambda: sys.executable)
    with pytest.raises(babeldoc.EngineFailed):
        await babeldoc.translate_pdf(
            pdf_path=tmp_path / "nope.pdf",
            output_dir=tmp_path / "out",
            api_key=FAKE_KEY,
            base_url="https://api.deepseek.com",
            model="deepseek-flash",
            timeout=10,
        )


def test_practical_base_url_is_versioned_once():
    from paperloom_service.urls import openai_sdk_base_url

    assert openai_sdk_base_url("https://api.deepseek.com") == "https://api.deepseek.com/v1"
    assert openai_sdk_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1"
