"""DeepSeek client (OpenAI-compatible), with retry, backoff and cancellation.

Docs verified 2026-11: base URL https://api.deepseek.com, models
`deepseek-flash` (vision, 1M context) and `deepseek-v4-pro`. Thinking mode is
on by default upstream, so translation requests explicitly disable it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger("paperloom.deepseek")


class DeepSeekError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


class _RateLimiter:
    def __init__(self, qps: float):
        self.qps = max(0.1, qps)
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._next - now
            self._next = max(now, self._next) + 1.0 / self.qps
        if wait > 0:
            await asyncio.sleep(wait)


def _endpoint(base_url: str, path: str) -> str:
    base = (base_url or "https://api.deepseek.com").rstrip("/")
    if base.endswith("/v1") or base.endswith("/beta"):
        return base + path
    return base + path


def _classify(status: int, body: str) -> DeepSeekError:
    message = body[:600]
    try:
        parsed = json.loads(body)
        err = parsed.get("error") or {}
        message = err.get("message") or parsed.get("message") or message
    except (json.JSONDecodeError, AttributeError):
        pass
    lowered = message.lower()
    if status == 401:
        return DeepSeekError("auth", f"DeepSeek 鉴权失败：{message}", status=status)
    if status == 402:
        return DeepSeekError("insufficient_balance", f"DeepSeek 余额不足：{message}", status=status)
    if status == 429:
        return DeepSeekError("rate_limit", f"DeepSeek 限流：{message}", retryable=True, status=status)
    if "context" in lowered and ("length" in lowered or "token" in lowered):
        return DeepSeekError("context_length", f"上下文超限：{message}", status=status)
    if status >= 500:
        return DeepSeekError("upstream", f"DeepSeek 服务端错误：{message}", retryable=True, status=status)
    if status == 400:
        return DeepSeekError("bad_request", f"DeepSeek 请求错误：{message}", status=status)
    return DeepSeekError("http", f"DeepSeek HTTP {status}：{message}", status=status)


def _fake_enabled() -> bool:
    return os.environ.get("PAPERLOOM_FAKE_LLM", "") not in ("", "0", "false", "False")


def estimate_tokens(text: str) -> int:
    """Rough estimate: CJK ~1 token/char, latin ~1 token/4 chars."""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = max(0, len(text) - cjk)
    return max(1, cjk + other // 4)


class DeepSeekClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
        connect_timeout: float = 15.0,
        max_retries: int = 3,
        qps: float = 4.0,
        concurrency: int = 4,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_retries = max(1, max_retries)
        self._limiter = _RateLimiter(qps)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=self.connect_timeout),
            follow_redirects=True,
        )

    async def _sleep_backoff(self, attempt: int) -> None:
        delay = min(20.0, 0.8 * (2**attempt)) * (0.7 + random.random() * 0.6)
        await asyncio.sleep(delay)

    async def chat_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        thinking: bool = False,
        json_mode: bool = False,
    ) -> AsyncIterator[dict]:
        """Yield {"type": "delta"|"usage"|"done"} events.

        Retries happen only before the first delta, so a partially rendered
        answer is never duplicated.
        """
        if _fake_enabled():
            async for event in self._fake_stream(messages, model=model, json_mode=json_mode):
                yield event
            return

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream_options": {"include_usage": True},
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        attempt = 0
        emitted = False
        while True:
            try:
                async with self._semaphore:
                    await self._limiter.acquire()
                    async with self._client() as client:
                        async with client.stream(
                            "POST",
                            _endpoint(self.base_url, "/chat/completions"),
                            headers=self._headers(),
                            json=payload,
                        ) as response:
                            if response.status_code >= 400:
                                body = (await response.aread()).decode("utf-8", "replace")
                                raise _classify(response.status_code, body)
                            async for event in self._iter_sse(response):
                                if event["type"] == "delta":
                                    emitted = True
                                yield event
                return
            except (httpx.TimeoutException,) as exc:
                err = DeepSeekError("timeout", f"DeepSeek 请求超时：{exc}", retryable=True)
            except httpx.HTTPError as exc:
                err = DeepSeekError("network", f"网络错误：{exc}", retryable=True)
            except DeepSeekError as exc:
                err = exc
            if emitted or not err.retryable or attempt + 1 >= self.max_retries:
                raise err
            attempt += 1
            log.warning("retrying DeepSeek request (attempt %s): %s", attempt, err.message)
            await self._sleep_backoff(attempt)

    async def _iter_sse(self, response: httpx.Response) -> AsyncIterator[dict]:
        usage: dict | None = None
        finish_reason: str | None = None
        async for raw in response.aiter_lines():
            line = raw.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                log.debug("ignoring malformed SSE chunk: %s", data[:120])
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    yield {"type": "delta", "text": text}
                reasoning = delta.get("reasoning_content")
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        if usage:
            yield {
                "type": "usage",
                "usage": {
                    "promptTokens": usage.get("prompt_tokens", 0),
                    "completionTokens": usage.get("completion_tokens", 0),
                    "totalTokens": usage.get("total_tokens", 0),
                    "estimated": False,
                },
            }
        yield {"type": "done", "finishReason": finish_reason}

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        thinking: bool = False,
        json_mode: bool = False,
    ) -> dict:
        """Non-streaming call with retries. Returns text + usage."""
        if _fake_enabled():
            text = _fake_text(messages, json_mode=json_mode)
            return {
                "text": text,
                "finish_reason": "stop",
                "usage": {
                    "promptTokens": estimate_tokens(json.dumps(messages, ensure_ascii=False)),
                    "completionTokens": estimate_tokens(text),
                    "estimated": True,
                },
            }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "thinking": {"type": "enabled" if thinking else "disabled"},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        attempt = 0
        while True:
            try:
                async with self._semaphore:
                    await self._limiter.acquire()
                    async with self._client() as client:
                        response = await client.post(
                            _endpoint(self.base_url, "/chat/completions"),
                            headers=self._headers(),
                            json=payload,
                        )
                if response.status_code >= 400:
                    raise _classify(response.status_code, response.text)
                data = response.json()
                choice = (data.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                usage = data.get("usage") or {}
                result_usage = {
                    "promptTokens": usage.get("prompt_tokens", 0),
                    "completionTokens": usage.get("completion_tokens", 0),
                    "totalTokens": usage.get("total_tokens", 0),
                    "estimated": not bool(usage),
                }
                if not usage:
                    result_usage["promptTokens"] = estimate_tokens(
                        json.dumps(messages, ensure_ascii=False)
                    )
                    result_usage["completionTokens"] = estimate_tokens(text)
                return {
                    "text": text,
                    "finish_reason": choice.get("finish_reason"),
                    "usage": result_usage,
                }
            except (httpx.TimeoutException,) as exc:
                err = DeepSeekError("timeout", f"DeepSeek 请求超时：{exc}", retryable=True)
            except httpx.HTTPError as exc:
                err = DeepSeekError("network", f"网络错误：{exc}", retryable=True)
            except DeepSeekError as exc:
                err = exc
            if not err.retryable or attempt + 1 >= self.max_retries:
                raise err
            attempt += 1
            log.warning("retrying DeepSeek request (attempt %s): %s", attempt, err.message)
            await self._sleep_backoff(attempt)

    async def test_connection(self, model: str) -> dict:
        started = time.perf_counter()
        result = await self.complete(
            [
                {"role": "system", "content": "You are a connectivity probe."},
                {"role": "user", "content": "Reply with the single word: ok"},
            ],
            model=model,
            max_tokens=8,
            temperature=0,
        )
        return {
            "ok": True,
            "model": model,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "reply": result["text"][:40],
            "usage": result["usage"],
        }

    async def _fake_stream(
        self, messages: list[dict], *, model: str, json_mode: bool
    ) -> AsyncIterator[dict]:
        text = _fake_text(messages, json_mode=json_mode)
        for index in range(0, len(text), 24):
            await asyncio.sleep(0)
            yield {"type": "delta", "text": text[index : index + 24]}
        yield {
            "type": "usage",
            "usage": {
                "promptTokens": estimate_tokens(json.dumps(messages, ensure_ascii=False)),
                "completionTokens": estimate_tokens(text),
                "estimated": True,
            },
        }
        yield {"type": "done", "finishReason": "stop"}


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _fake_text(messages: list[dict], *, json_mode: bool) -> str:
    user = _last_user_text(messages)
    ids = re.findall(r"\[\[SEG:([^\]]+)\]\]\s*([^\n]*)", user)
    if ids and ("translations" in user or json_mode):
        payload = {
            "translations": [
                {"id": seg_id, "text": f"【模拟译文】{text[:120]}"} for seg_id, text in ids
            ]
        }
        return json.dumps(payload, ensure_ascii=False)
    # Chat/analysis prompts put the document context in the system message, so
    # look at the whole conversation before giving up on citations.
    full = "\n".join(str(m.get("content", "")) for m in messages)
    citations = re.findall(r"\[\[SEG:([^\]]+)\]\]", full)
    marker = f" [[seg:{citations[0]}]]" if citations else ""
    if json_mode:
        return json.dumps(
            {"answer": "模拟模式：未配置真实 API Key，此回答由本地假实现生成。" + marker},
            ensure_ascii=False,
        )
    return "模拟模式：未配置真实 API Key，此回答由本地假实现生成。" + marker
