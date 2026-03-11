"""Centralized OpenRouter LLM client for channel agent."""

from __future__ import annotations

import re
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response, log_usage
from app.agent.channel.http import close_http_client, get_http_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.llm_client")


def _is_transient_error(exc: BaseException) -> bool:
    """Only retry on timeouts and transient HTTP status codes (429, 5xx)."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503, 504)
    return False


# Retry transient HTTP errors (429, 502, 503, 504, timeouts) with exponential backoff
_TRANSIENT_RETRY = retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


def _get_client(timeout: int = 30) -> httpx.AsyncClient:
    """Return the shared httpx client. Delegates to http.get_http_client()."""
    return get_http_client(timeout=timeout)


async def close_client() -> None:
    """Close the shared httpx client."""
    await close_http_client()


_CODE_FENCE_RE = re.compile(r"^```(?:json|html|text)?\s*\n?", re.MULTILINE)
_CODE_FENCE_END_RE = re.compile(r"\n?```\s*$", re.MULTILINE)


async def openrouter_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    operation: str,
    channel_id: str = "",
    temperature: float = 0.3,
    timeout: int = 30,
    strip_code_fences: bool = True,
    tools: list[dict[str, Any]] | None = None,
    raw_response: bool = False,
) -> str | dict[str, Any] | None:
    """Make a chat completion request to OpenRouter.

    Returns the content string or None on failure.
    Automatically tracks usage costs and strips markdown code fences.

    If raw_response=True, returns the full message dict (for tool calling).
    """
    base_url = settings.agent.openrouter_base_url

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools

    @_TRANSIENT_RETRY
    async def _call() -> dict[str, Any]:
        client = _get_client()
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/moderator-bot",
            },
            json=payload,
            timeout=httpx.Timeout(timeout),
        )
        resp.raise_for_status()
        return resp.json()

    data = await _call()

    # Track usage
    usage = extract_usage_from_openrouter_response(data, model=model, operation=operation, channel_id=channel_id)
    if usage:
        await log_usage(usage)

    message = data["choices"][0]["message"]

    if raw_response:
        return message

    content = message.get("content") or ""

    if strip_code_fences and content:
        content = _CODE_FENCE_RE.sub("", content)
        content = _CODE_FENCE_END_RE.sub("", content)
        content = content.strip()

    return content or None
