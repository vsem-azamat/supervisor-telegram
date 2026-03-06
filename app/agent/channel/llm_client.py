"""Centralized OpenRouter LLM client for channel agent."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response, log_usage
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.llm_client")

_client: httpx.AsyncClient | None = None


def _get_client(timeout: int = 30) -> httpx.AsyncClient:
    """Return a reusable httpx client, creating one if needed."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=timeout)
    return _client


async def close_client() -> None:
    """Close the module-level httpx client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


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
    data = resp.json()

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
