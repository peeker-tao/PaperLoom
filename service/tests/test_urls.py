"""Base URL normalization tests (issue: duplicated /v1 path)."""

from __future__ import annotations

import pytest

from paperloom_service.urls import (
    OFFICIAL_BASE_URL,
    chat_completions_url,
    check_base_url,
    join_url,
    normalize_base_url,
    openai_sdk_base_url,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, OFFICIAL_BASE_URL),
        ("", OFFICIAL_BASE_URL),
        ("   ", OFFICIAL_BASE_URL),
        (OFFICIAL_BASE_URL, OFFICIAL_BASE_URL),
        ("https://api.deepseek.com/", OFFICIAL_BASE_URL),
        ("https://api.deepseek.com///", OFFICIAL_BASE_URL),
        ("api.deepseek.com", OFFICIAL_BASE_URL),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1/chat/completions", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/chat/completions", OFFICIAL_BASE_URL),
        ("https://gateway.example.com/deepseek", "https://gateway.example.com/deepseek"),
        ("https://gateway.example.com/deepseek/v1/", "https://gateway.example.com/deepseek/v1"),
        ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_normalize_rejects_bad_scheme():
    with pytest.raises(ValueError):
        normalize_base_url("ftp://example.com")
    with pytest.raises(ValueError):
        normalize_base_url("https://")


@pytest.mark.parametrize(
    "base,expected",
    [
        (OFFICIAL_BASE_URL, "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"),
        (
            "https://api.deepseek.com/v1/chat/completions",
            "https://api.deepseek.com/v1/chat/completions",
        ),
        (
            "https://gateway.example.com/deepseek/v1",
            "https://gateway.example.com/deepseek/v1/chat/completions",
        ),
    ],
)
def test_chat_completions_url_never_duplicates_version(base, expected):
    url = chat_completions_url(base)
    assert url == expected
    assert url.count("/v1") == expected.count("/v1")


@pytest.mark.parametrize(
    "base,expected",
    [
        (OFFICIAL_BASE_URL, "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com/v1"),
        ("https://api.deepseek.com/beta", "https://api.deepseek.com/beta"),
        ("https://gateway.example.com/deepseek", "https://gateway.example.com/deepseek/v1"),
        ("https://gateway.example.com/deepseek/v1", "https://gateway.example.com/deepseek/v1"),
    ],
)
def test_openai_sdk_base_url_preserves_proxy_prefix(base, expected):
    assert openai_sdk_base_url(base) == expected


def test_join_url_handles_relative_path_without_slash():
    assert join_url(OFFICIAL_BASE_URL, "models") == "https://api.deepseek.com/models"


def test_check_base_url_reports_endpoints():
    check = check_base_url("https://api.deepseek.com/v1/")
    assert check.ok
    assert check.normalized == "https://api.deepseek.com/v1"
    assert check.endpoint == "https://api.deepseek.com/v1/chat/completions"
    assert check.sdk_base == "https://api.deepseek.com/v1"
    assert "/v1/v1" not in check.endpoint
    assert not check.as_dict()["message"].startswith("地址无效")


def test_check_base_url_flags_invalid_input():
    check = check_base_url("ftp://example.com")
    assert check.ok is False
    assert "地址无效" in check.message


def test_check_base_url_warns_on_plain_http():
    check = check_base_url("http://paper-proxy.example.com")
    assert check.ok
    assert "明文 HTTP" in check.message


def test_check_base_url_notes_loopback():
    check = check_base_url("http://127.0.0.1:8080")
    assert check.ok
    assert "本机地址" in check.message
