"""Centralized OpenRouter LLM client for channel agent."""

from __future__ import annotations

import re

import httpx

from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response, log_usage
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.llm_client")

_CODE_FENCE_RE = re.compile(r"^```(?:json|html|text)?\s*\n?", re.MULTILINE)
_CODE_FENCE_END_RE = re.compile(r"\n?```\s*$", re.MULTILINE)


async def openrouter_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    operation: str,
    channel_id: str = "",
    temperature: float = 0.3,
    timeout: int = 30,
    strip_code_fences: bool = True,
) -> str | None:
    """Make a chat completion request to OpenRouter.

    Returns the content string or None on failure.
    Automatically tracks usage costs and strips markdown code fences.
    """
    base_url = settings.agent.openrouter_base_url

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/moderator-bot",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # Track usage
    usage = extract_usage_from_openrouter_response(data, model=model, operation=operation, channel_id=channel_id)
    if usage:
        await log_usage(usage)

    content = data["choices"][0]["message"]["content"]

    if strip_code_fences and content:
        content = _CODE_FENCE_RE.sub("", content)
        content = _CODE_FENCE_END_RE.sub("", content)
        content = content.strip()

    return content
