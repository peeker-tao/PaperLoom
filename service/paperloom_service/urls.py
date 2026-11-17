"""Base URL normalization shared by every outbound caller.

Different consumers need different shapes:

* ``DeepSeekClient`` posts to an explicit ``/chat/completions`` endpoint.
* BabelDOC hands its ``openai-base-url`` to the OpenAI SDK, which appends the
  path itself, so it expects a versioned root such as ``.../v1``.

Nothing here may duplicate a version segment (``/v1/v1``) or drop a proxy path
prefix (``https://gateway.example.com/deepseek``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

OFFICIAL_BASE_URL = "https://api.deepseek.com"

# Paths users commonly paste instead of the root.
_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/responses",
    "/messages",
    "/models",
)

_VERSION_SEGMENT = re.compile(r"/(v\d+[a-z0-9]*|beta)$", re.IGNORECASE)


def normalize_base_url(raw: str | None) -> str:
    """Return a canonical ``scheme://host[:port]/path`` without a trailing slash.

    Raises ``ValueError`` for inputs that cannot be a usable HTTP base.
    """
    value = (raw or "").strip()
    if not value:
        return OFFICIAL_BASE_URL
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"}:
        raise ValueError(f"不支持的协议：{parts.scheme}")
    if not parts.netloc:
        raise ValueError("缺少主机名")
    path = re.sub(r"/{2,}", "/", parts.path or "")
    for suffix in _ENDPOINT_SUFFIXES:
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)]
            break
    path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def join_url(base: str | None, path: str) -> str:
    """Join a normalized base with a path, never doubling the slash."""
    root = normalize_base_url(base)
    if not path.startswith("/"):
        path = "/" + path
    return root + path


def chat_completions_url(base: str | None) -> str:
    return join_url(base, "/chat/completions")


def openai_sdk_base_url(base: str | None) -> str:
    """Base URL for SDKs that append ``/chat/completions`` themselves.

    A versioned base (``/v1``, ``/beta``, ``/v1beta``...) is preserved; a bare
    host or proxy prefix gets exactly one ``/v1`` appended.
    """
    root = normalize_base_url(base)
    if _VERSION_SEGMENT.search(root):
        return root
    return root + "/v1"


@dataclass
class UrlCheck:
    ok: bool
    normalized: str
    endpoint: str
    sdk_base: str
    message: str

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "normalized": self.normalized,
            "endpoint": self.endpoint,
            "sdkBase": self.sdk_base,
            "message": self.message,
        }


def check_base_url(raw: str | None) -> UrlCheck:
    """Validate a user-supplied base URL and describe the derived endpoints."""
    try:
        root = normalize_base_url(raw)
    except ValueError as exc:
        return UrlCheck(
            ok=False,
            normalized="",
            endpoint="",
            sdk_base="",
            message=f"地址无效：{exc}",
        )
    endpoint = chat_completions_url(root)
    sdk_base = openai_sdk_base_url(root)
    parts = urlsplit(root)
    message = f"聊天端点：{endpoint}"
    if parts.hostname in {"localhost", "127.0.0.1", "::1"}:
        message += "（本机地址，请确认代理已启动）"
    elif parts.scheme == "http":
        message += "（使用明文 HTTP，密钥会以明文传输）"
    if _VERSION_SEGMENT.search(root):
        message += f"；已包含版本段，BabelDOC 使用 {sdk_base}"
    else:
        message += f"；BabelDOC 将使用 {sdk_base}"
    return UrlCheck(
        ok=True, normalized=root, endpoint=endpoint, sdk_base=sdk_base, message=message
    )
