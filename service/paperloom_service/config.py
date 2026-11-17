"""Runtime configuration and secure secret storage.

The API key is stored with Windows DPAPI when available, otherwise in a
0600 file. It is never written to logs.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("paperloom")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_TRANSLATE_MODEL = "deepseek-flash"
DEFAULT_CHAT_MODEL = "deepseek-flash"
DEFAULT_ANALYSIS_MODEL = "deepseek-v4-pro"

# USD per 1M tokens, from https://api-docs.deepseek.com/quick_start/pricing
# (2026-11). Users can override these in pricing.json.
DEFAULT_PRICING = {
    "deepseek-flash": {
        "input_cache_hit": 0.006,
        "input_cache_miss": 0.30,
        "output": 1.20,
        "off_peak_multiplier": 0.5,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.044,
        "input_cache_miss": 1.32,
        "output": 3.96,
        "off_peak_multiplier": 0.5,
    },
}


def default_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "PaperLoom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PaperLoom"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "PaperLoom"


@dataclass
class Settings:
    base_url: str = DEFAULT_BASE_URL
    translate_model: str = DEFAULT_TRANSLATE_MODEL
    chat_model: str = DEFAULT_CHAT_MODEL
    analysis_model: str = DEFAULT_ANALYSIS_MODEL
    timeout_seconds: float = 120.0
    connect_timeout_seconds: float = 15.0
    concurrency: int = 4
    qps: float = 4.0
    max_retries: int = 3
    context_chars: int = 24000
    max_output_tokens: int = 8192
    thinking: bool = False
    babeldoc_enabled: bool = True
    babeldoc_timeout: float = 3600.0

    def public(self) -> dict:
        data = asdict(self)
        return data


@dataclass
class RuntimeConfig:
    data_dir: Path = field(default_factory=default_data_dir)
    host: str = "127.0.0.1"
    port: int = 23124
    token: str = ""
    log_level: str = "INFO"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def pricing_path(self) -> Path:
        return self.data_dir / "pricing.json"

    @property
    def secret_path(self) -> Path:
        return self.data_dir / "secret.bin"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.files_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)


def _load_token(cfg: RuntimeConfig) -> str:
    env = os.environ.get("PAPERLOOM_TOKEN")
    if env:
        return env
    path = cfg.data_dir / "token"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(32)
    path.write_text(value, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - platform dependent
        pass
    return value


def load_runtime(port: int | None = None) -> RuntimeConfig:
    data_dir = Path(os.environ.get("PAPERLOOM_DATA_DIR") or default_data_dir())
    cfg = RuntimeConfig(data_dir=data_dir)
    cfg.ensure_dirs()
    if port:
        cfg.port = port
    else:
        cfg.port = int(os.environ.get("PAPERLOOM_PORT") or 23124)
    cfg.token = _load_token(cfg)
    cfg.log_level = os.environ.get("PAPERLOOM_LOG_LEVEL", "INFO").upper()
    return cfg


def load_settings(cfg: RuntimeConfig) -> Settings:
    settings = Settings()
    if cfg.settings_path.exists():
        try:
            raw = json.loads(cfg.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("settings.json is unreadable; using defaults")
            raw = {}
        for key, value in raw.items():
            if hasattr(settings, key) and not key.startswith("_"):
                setattr(settings, key, value)
    return settings


def save_settings(cfg: RuntimeConfig, settings: Settings) -> None:
    cfg.settings_path.write_text(
        json.dumps(settings.public(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Secret storage
# --------------------------------------------------------------------------- #

_DPAPI_PREFIX = b"dpapi:"


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi_protect(data: bytes) -> bytes:  # pragma: no cover - windows only
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:  # pragma: no cover - windows only
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def save_api_key(cfg: RuntimeConfig, key: str) -> None:
    key = key.strip()
    if not key:
        clear_api_key(cfg)
        return
    payload = key.encode("utf-8")
    if _dpapi_available():
        blob = _DPAPI_PREFIX + _dpapi_protect(payload)
    else:
        blob = payload
    cfg.secret_path.write_bytes(blob)
    try:
        os.chmod(cfg.secret_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover
        pass


def load_api_key(cfg: RuntimeConfig) -> str:
    if cfg.secret_path.exists():
        blob = cfg.secret_path.read_bytes()
        try:
            if blob.startswith(_DPAPI_PREFIX):
                return _dpapi_unprotect(blob[len(_DPAPI_PREFIX) :]).decode("utf-8")
            return blob.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            log.warning("stored API key could not be decrypted; ignoring it")
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def clear_api_key(cfg: RuntimeConfig) -> None:
    try:
        cfg.secret_path.unlink()
    except FileNotFoundError:
        pass


def api_key_status(cfg: RuntimeConfig) -> dict:
    key = load_api_key(cfg)
    source = "none"
    if key:
        source = "env" if not cfg.secret_path.exists() and os.environ.get("DEEPSEEK_API_KEY") else "store"
    return {"configured": bool(key), "source": source, "hint": _mask(key)}


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * 8}{key[-4:]}"


def load_pricing(cfg: RuntimeConfig) -> dict:
    if cfg.pricing_path.exists():
        try:
            return json.loads(cfg.pricing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("pricing.json is unreadable; using defaults")
    cfg.pricing_path.write_text(json.dumps(DEFAULT_PRICING, indent=2), encoding="utf-8")
    return DEFAULT_PRICING


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int, pricing: dict) -> float | None:
    entry = pricing.get(model)
    if not entry:
        return None
    # Without cache reporting we assume cache miss pricing (upper bound).
    usd = (
        prompt_tokens / 1_000_000 * float(entry.get("input_cache_miss", 0))
        + completion_tokens / 1_000_000 * float(entry.get("output", 0))
    )
    return round(usd, 6)


def encode_blob(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
