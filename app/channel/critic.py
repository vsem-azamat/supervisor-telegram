"""Post critic: polish pass that removes clichés while preserving facts/links/structure.

Invoked from `generate_post` after length-enforcement, before the image pipeline.
On any failure the pipeline keeps the original text (silent fallback).
"""

from __future__ import annotations

import re
import unicodedata

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage
from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import get_logger

logger = get_logger("channel.critic")


class CriticError(DomainError):
    """Raised when the critic pass fails after retry (invariants still violated)."""


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Whitelist of headline emojis used by the generation prompt. Any of these
# at the first non-whitespace codepoint is considered a valid headline emoji.
_HEADLINE_EMOJIS = frozenset({"📰", "🎓", "💼", "🎉", "🏠", "💰", "⚡", "✨", "🔥", "⭐"})

_MIN_LENGTH = 100
_MAX_LENGTH = 900


def _extract_md_links(text: str) -> list[tuple[str, str]]:
    """Return list of (label, url) pairs from Markdown links `[label](url)`."""
    return [(m.group(1), m.group(2)) for m in _LINK_RE.finditer(text)]


def _strip_agent_artifacts(output: str) -> str:
    """Strip common LLM artifacts: code fences, prefix phrases, surrounding quotes.

    Applied before invariant validation so benign formatting cruft doesn't
    trigger failures.
    """
    text = output.strip()

    # 1. Code fence (```lang ... ```), optionally with language tag.
    fence = re.match(
        r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```$",
        text,
        flags=re.DOTALL,
    )
    if fence:
        text = fence.group(1).strip()

    # 2. Common prefix phrases like "Here's the polished version:"
    prefix_patterns = [
        r"^here'?s?\s+(?:the|your|a)?\s*polished\s+(?:version|post)?:?\s*\n+",
        r"^polished\s+(?:version|post):?\s*\n+",
        r"^here\s+is\s+(?:the|your)?\s*polished\s+(?:version|post)?:?\s*\n+",
    ]
    for pat in prefix_patterns:
        text = re.sub(pat, "", text, count=1, flags=re.IGNORECASE).strip()

    # 3. Surrounding quotes.
    if len(text) >= 2 and text[0] in {'"', "'", "«", "\u201c"} and text[-1] in {'"', "'", "»", "\u201d"}:
        text = text[1:-1].strip()

    return text


def _first_visible_char(text: str) -> str:
    """Return the first non-whitespace character of `text`, or empty string."""
    for ch in text:
        if not ch.isspace():
            return ch
    return ""


def _validate_invariants(original: str, polished: str, footer: str) -> list[str]:
    """Return a list of human-readable violation strings. Empty list = all pass."""
    violations: list[str] = []

    orig_links = _extract_md_links(original)
    new_links = _extract_md_links(polished)

    orig_urls = {url for _, url in orig_links}
    new_urls = {url for _, url in new_links}

    missing = orig_urls - new_urls
    for url in missing:
        violations.append(f"lost URL: {url}")

    if len(new_links) < len(orig_links):
        violations.append(f"link count dropped: {len(orig_links)} → {len(new_links)}")

    if footer and footer not in polished:
        violations.append("footer missing")

    if len(polished) > _MAX_LENGTH:
        violations.append(f"length over 900: {len(polished)}")

    if len(polished) < _MIN_LENGTH:
        violations.append(f"output too short: {len(polished)} (min {_MIN_LENGTH})")

    first = _first_visible_char(polished)
    if first and first not in _HEADLINE_EMOJIS:
        # Fallback: check the whole first codepoint is in the Symbol,Other
        # Unicode category (emoji-ish). `first` is a single character from the
        # Python string; compare its category via `unicodedata`.
        cat = unicodedata.category(first)
        if not cat.startswith("So"):
            violations.append(f"headline emoji missing (first char: {first!r})")

    return violations


# ── LLM critic pass ──────────────────────────────────────────────────

CRITIC_PROMPT = """\
You are a ruthless style editor for the Telegram channel "Konnekt"
(news for CIS students in the Czech Republic). Your ONLY job: polish a
post by removing clichés, banal openers, dead verbs, and pompous or
corporate phrasing.

HARD RULES — violation = task failed:
1. PRESERVE every Markdown link [text](url) — same URLs, same count.
2. PRESERVE the exact footer at the end: {footer}
3. PRESERVE facts: numbers, dates, names, institutions, prices, addresses.
4. PRESERVE structure: same paragraph breaks, same order, same headline
   emoji at the very start.
5. Output MUST be <= 900 characters total.
6. Do NOT add new information. Do NOT invent details, numbers, or names.

WHAT TO FIX:
- Banned phrases: "это отличная/уникальная возможность",
  "не упустите шанс", "лично расспросить", "рады сообщить",
  "с гордостью представляем", "Ознакомиться можно...",
  "Подробнее здесь...", "Узнать больше..."
- Banal openers: "У нас отличная новость", "Есть хорошая новость для
  вас", "Хотим поделиться..."
- Dead verbs: "предоставляем", "сообщаем", "уведомляем" — replace with
  the concrete action.
- Pompous / corporate tone → friendly, peer-to-peer student tone.
- Filler adjectives: "уникальный", "незабываемый", "эксклюзивный".

TONE: simple, slightly witty, like telling a friend about news. At
most one exclamation mark per post.

OUTPUT: return ONLY the polished post text. No explanations, no
"Here's your polished version:", no markdown code fences. Plain
polished post.
"""

_RETRY_HINT = (
    "Your previous rewrite violated hard rules. Fix the violations and "
    "return ONLY the polished post text.\n"
    "You MUST preserve every link [text](url), the exact footer, the "
    "headline emoji, and keep the total length <= 900 characters.\n"
)


def _create_critic_agent(api_key: str, model: str, *, footer: str) -> Agent[None, str]:
    """Build the PydanticAI agent for the critic pass."""
    provider = OpenAIProvider(base_url=settings.openrouter.base_url, api_key=api_key)
    llm = OpenAIChatModel(model_name=model, provider=provider)
    prompt = CRITIC_PROMPT.format(footer=footer)
    return Agent(llm, system_prompt=prompt, output_type=str, model_settings={"temperature": 0.4})


async def polish_post(
    *,
    text: str,
    footer: str,
    api_key: str,
    model: str,
) -> str:
    """Run the critic pass on `text`. Returns polished text or raises CriticError.

    Makes at most two LLM calls: the main polish, plus one retry if the
    first result violates invariants. On any exception (LLM error, retry
    still violates), raises CriticError so the caller can fall back.
    """
    agent = _create_critic_agent(api_key, model, footer=footer)

    try:
        result = await agent.run(text)
    except Exception as exc:
        raise CriticError(f"first call failed: {exc}") from exc

    usage = extract_usage_from_pydanticai_result(result, model, "critic")
    if usage:
        await log_usage(usage)

    polished = _strip_agent_artifacts(result.output)
    violations = _validate_invariants(text, polished, footer)
    if not violations:
        return polished

    logger.info("critic_retry", violations=violations)

    retry_prompt = f"{_RETRY_HINT}Previous violations: {', '.join(violations)}\n\nOriginal post (rewrite this):\n{text}"

    try:
        result = await agent.run(retry_prompt)
    except Exception as exc:
        raise CriticError(f"retry call failed: {exc}") from exc

    usage = extract_usage_from_pydanticai_result(result, model, "critic_retry")
    if usage:
        await log_usage(usage)

    polished = _strip_agent_artifacts(result.output)
    violations = _validate_invariants(text, polished, footer)
    if not violations:
        return polished

    raise CriticError(f"invariants violated after retry: {violations}")
