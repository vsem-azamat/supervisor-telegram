# Critic Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-generation polish pass (Claude Sonnet 4.6) that removes clichés, banal openers, dead verbs, and pompous phrasing while preserving facts, links, footer, structure, and length, behind a global + per-channel kill switch.

**Architecture:** New `app/channel/critic.py` module with a `polish_post()` entrypoint invoked from `generate_post()` after length-enforcement and before the image pipeline. Silent fallback on any failure (retry once, then return original text). Per-channel override `channels.critic_enabled` resolves against global `settings.channel.critic_enabled`. Original text preserved in `channel_posts.pre_critic_text` for audit/diff.

**Tech Stack:** PydanticAI Agent + OpenAIChatModel via OpenRouter, SQLAlchemy 2.x async, Alembic, pytest, pytest-asyncio.

---

## File map

**New:**
- `app/channel/critic.py` — polish pass, invariants, agent builder, `resolve_critic_enabled`
- `alembic/versions/<hash>_add_critic_columns.py` — two-column migration
- `tests/unit/test_critic_config.py`
- `tests/unit/test_critic_columns.py`
- `tests/unit/test_critic_invariants.py`
- `tests/unit/test_critic_polish.py`
- `tests/unit/test_critic_resolve.py`
- `tests/integration/test_generator_with_critic.py`
- `tests/unit/test_assistant_set_channel_critic.py`

**Modified:**
- `app/channel/config.py` — `critic_enabled`, `critic_model` fields
- `app/db/models.py` — `Channel.critic_enabled`, `ChannelPost.pre_critic_text`, `__init__` kwargs, `GeneratedPost` is in `generator.py`
- `app/channel/generator.py` — `GeneratedPost.pre_critic_text`, new kwargs on `generate_post`, critic invocation
- `app/channel/workflow.py` — resolve critic flags, pass to generator
- `app/channel/review/service.py` — persist `pre_critic_text` in `create_review_post`; regen path mirrors workflow
- `app/assistant/tools/channel/channels.py` — `set_channel_critic` tool

---

## Task 1: Add config fields

Adds the global master switch and model selection to `ChannelAgentSettings`.

**Files:**
- Modify: `app/channel/config.py`
- Create: `tests/unit/test_critic_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_critic_config.py`:

```python
"""Tests for critic-related settings on ChannelAgentSettings."""

from __future__ import annotations

from app.channel.config import ChannelAgentSettings


def test_critic_enabled_default_false():
    s = ChannelAgentSettings()
    assert s.critic_enabled is False


def test_critic_model_default_sonnet():
    s = ChannelAgentSettings()
    assert s.critic_model == "anthropic/claude-sonnet-4-6"


def test_critic_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_CRITIC_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_CRITIC_MODEL", "openai/gpt-5.1")
    s = ChannelAgentSettings()
    assert s.critic_enabled is True
    assert s.critic_model == "openai/gpt-5.1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_config.py -v`
Expected: FAIL with `AttributeError` / `no attribute 'critic_enabled'`.

- [ ] **Step 3: Add the fields**

In `app/channel/config.py`, inside `class ChannelAgentSettings(BaseSettings)`, add after the `temperature` field (around line 60):

```python
    critic_enabled: bool = Field(
        default=False,
        description="Master kill-switch for the post critic polish pass",
    )
    critic_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="Model used by the critic agent",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_critic_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/channel/config.py tests/unit/test_critic_config.py
git commit -m "feat(critic): add critic_enabled and critic_model config fields"
```

---

## Task 2: DB migration + ORM columns

Adds `channels.critic_enabled` (nullable bool) and `channel_posts.pre_critic_text` (nullable text), updates ORM models and their `__init__` methods.

**Files:**
- Create: `alembic/versions/<hash>_add_critic_columns.py`
- Modify: `app/db/models.py`
- Create: `tests/unit/test_critic_columns.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_critic_columns.py`:

```python
"""Tests for critic DB columns on Channel and ChannelPost."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost

pytestmark = pytest.mark.asyncio


async def test_channel_critic_enabled_default_none(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1001, name="X")
        session.add(ch)
        await session.commit()
        await session.refresh(ch)
        assert ch.critic_enabled is None


async def test_channel_critic_enabled_roundtrip(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1002, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()
        cid = ch.id

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    assert row.critic_enabled is True


async def test_channel_critic_enabled_explicit_false(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1003, name="X", critic_enabled=False)
        session.add(ch)
        await session.commit()
        cid = ch.id

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    assert row.critic_enabled is False


async def test_channel_post_pre_critic_text_default_none(session_maker):
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        assert p.pre_critic_text is None


async def test_channel_post_pre_critic_text_roundtrip(session_maker):
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="y",
            title="t",
            post_text="new",
            status=PostStatus.DRAFT,
            pre_critic_text="original pre-critic text with **bold**",
        )
        session.add(p)
        await session.commit()
        pid = p.id

    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
    assert row.pre_critic_text == "original pre-critic text with **bold**"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_columns.py -v`
Expected: FAIL — `critic_enabled` / `pre_critic_text` unknown kwarg / attribute.

- [ ] **Step 3: Add `critic_enabled` to `Channel`**

In `app/db/models.py`, inside `class Channel`, add the column declaration next to `enabled` (around line 273):

```python
    critic_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

Update `Channel.__init__` signature (around line 279-306) to accept and assign it:

```python
    def __init__(
        self,
        telegram_id: int,
        name: str,
        description: str = "",
        language: str = "ru",
        review_chat_id: int | None = None,
        max_posts_per_day: int = 3,
        posting_schedule: list[str] | None = None,
        discovery_query: str = "",
        source_discovery_query: str = "",
        username: str | None = None,
        footer_template: str | None = None,
        enabled: bool = True,
        critic_enabled: bool | None = None,
    ) -> None:
        self.telegram_id = telegram_id
        self.name = name
        self.description = description
        self.language = language
        self.review_chat_id = review_chat_id
        self.max_posts_per_day = max_posts_per_day
        self.posting_schedule = posting_schedule
        self.discovery_query = discovery_query
        self.source_discovery_query = source_discovery_query
        self.username = username
        self.footer_template = footer_template
        self.enabled = enabled
        self.critic_enabled = critic_enabled
```

- [ ] **Step 4: Add `pre_critic_text` to `ChannelPost`**

In `app/db/models.py`, inside `class ChannelPost`, add the column declaration near `admin_feedback` (around line 415):

```python
    pre_critic_text: Mapped[str | None] = mapped_column(String, nullable=True)
```

Update `ChannelPost.__init__` signature (around line 425-462) to accept `pre_critic_text`:

```python
    def __init__(
        self,
        channel_id: int,
        external_id: str,
        title: str,
        post_text: str,
        source_url: str | None = None,
        source_items: list[dict[str, Any]] | None = None,
        telegram_message_id: int | None = None,
        review_message_id: int | None = None,
        review_chat_id: int | None = None,
        review_album_message_ids: list[int] | None = None,
        image_url: str | None = None,
        image_urls: list[str] | None = None,
        image_candidates: list[dict[str, Any]] | None = None,
        image_phashes: list[str] | None = None,
        status: str = PostStatus.DRAFT,
        embedding: Any | None = None,
        embedding_model: str | None = None,
        pre_critic_text: str | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.external_id = external_id
        self.title = title
        self.post_text = post_text
        self.source_url = source_url
        self.source_items = source_items
        self.telegram_message_id = telegram_message_id
        self.review_message_id = review_message_id
        self.review_chat_id = review_chat_id
        self.image_url = image_url
        self.image_urls = image_urls
        self.image_candidates = image_candidates
        self.image_phashes = image_phashes
        self.status = status
        self.reply_chain_message_ids: list[int] | None = None
        self.review_album_message_ids = review_album_message_ids
        self.embedding = embedding
        self.embedding_model = embedding_model
        self.pre_critic_text = pre_critic_text
```

- [ ] **Step 5: Generate the Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add critic_enabled and pre_critic_text"`

This writes a file like `alembic/versions/<hash>_add_critic_enabled_and_pre_critic_text.py`. Open that file and verify its `upgrade()` contains exactly these two operations and nothing else (if autogenerate pulls in unrelated drift — which has happened before on this repo — edit the file to keep only the two operations):

```python
def upgrade() -> None:
    op.add_column("channels", sa.Column("critic_enabled", sa.Boolean(), nullable=True))
    op.add_column("channel_posts", sa.Column("pre_critic_text", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_posts", "pre_critic_text")
    op.drop_column("channels", "critic_enabled")
```

Ensure `down_revision` points to the current head `"21c84750b5db"`. Autogenerate fills this in automatically.

- [ ] **Step 6: Run the test suite to verify the migration and columns**

Run: `uv run -m pytest tests/unit/test_critic_columns.py -v`
Expected: 5 passed.

Additionally sanity-check by running the broader ORM test file so we catch regressions in the model `__init__` signatures:

Run: `uv run -m pytest tests/unit -k "channel" -v`
Expected: all existing channel-related tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/db/models.py alembic/versions tests/unit/test_critic_columns.py
git commit -m "feat(critic): add critic_enabled + pre_critic_text columns"
```

---

## Task 3: Add `pre_critic_text` to `GeneratedPost`

The pydantic model used by the generator needs a field to carry the original text through the pipeline.

**Files:**
- Modify: `app/channel/generator.py` (lines 64-77 — `class GeneratedPost`)
- Test: `tests/unit/test_critic_columns.py` (adding a small assertion; no new file)

- [ ] **Step 1: Write a failing test**

Append to `tests/unit/test_critic_columns.py`:

```python
def test_generated_post_pre_critic_text_default_none():
    from app.channel.generator import GeneratedPost

    p = GeneratedPost(text="hello")
    assert p.pre_critic_text is None


def test_generated_post_pre_critic_text_roundtrip():
    from app.channel.generator import GeneratedPost

    p = GeneratedPost(text="new text", pre_critic_text="original text")
    assert p.pre_critic_text == "original text"

    dumped = p.model_dump()
    restored = GeneratedPost.model_validate(dumped)
    assert restored.pre_critic_text == "original text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_columns.py::test_generated_post_pre_critic_text_default_none tests/unit/test_critic_columns.py::test_generated_post_pre_critic_text_roundtrip -v`
Expected: FAIL — `pre_critic_text` not a valid field.

- [ ] **Step 3: Add the field**

In `app/channel/generator.py`, modify `class GeneratedPost` (around line 64) to add the field after `image_phashes`:

```python
class GeneratedPost(BaseModel):
    """Output from the post generation agent."""

    text: str = Field(description="The post text in Markdown format")
    is_sensitive: bool = Field(default=False, description="Whether the post needs admin review")
    image_url: str | None = Field(default=None, description="Primary image URL (backward compat)")
    image_urls: list[str] = Field(default_factory=list, description="All image URLs for the post")
    image_candidates: list[dict[str, Any]] | None = Field(
        default=None, description="Full candidate pool with scores and metadata (for review agent)"
    )
    image_phashes: list[str] = Field(
        default_factory=list, description="pHashes of selected images (for future cross-post dedup)"
    )
    pre_critic_text: str | None = Field(
        default=None,
        description="Post text before the critic polish pass; None when critic did not run or failed",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_critic_columns.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/channel/generator.py tests/unit/test_critic_columns.py
git commit -m "feat(critic): add pre_critic_text to GeneratedPost"
```

---

## Task 4: Critic module — helpers and invariant validation

Adds the structural pieces of `app/channel/critic.py`: exception, link extraction, artifact stripping, invariant validation. The actual `polish_post` lands in Task 5.

**Files:**
- Create: `app/channel/critic.py`
- Create: `tests/unit/test_critic_invariants.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_critic_invariants.py`:

```python
"""Tests for critic helpers: link extraction, artifact stripping, invariant validation."""

from __future__ import annotations

from app.channel.critic import (
    CriticError,
    _extract_md_links,
    _strip_agent_artifacts,
    _validate_invariants,
)

FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"


def test_extract_md_links_empty():
    assert _extract_md_links("") == []


def test_extract_md_links_none():
    assert _extract_md_links("plain text no links") == []


def test_extract_md_links_single():
    out = _extract_md_links("Check [platform](https://example.com/x) today")
    assert out == [("platform", "https://example.com/x")]


def test_extract_md_links_multiple():
    out = _extract_md_links("See [a](http://x/1) and [b](http://y/2)")
    assert out == [("a", "http://x/1"), ("b", "http://y/2")]


def test_extract_md_links_ignores_malformed():
    assert _extract_md_links("broken [text(no close http://x)") == []


def test_strip_agent_artifacts_clean_passthrough():
    text = "🎓 **Headline**\n\nBody.\n\n" + FOOTER
    assert _strip_agent_artifacts(text) == text


def test_strip_agent_artifacts_code_fence():
    text = "```\n🎓 **H**\n\nBody.\n```"
    assert _strip_agent_artifacts(text) == "🎓 **H**\n\nBody."


def test_strip_agent_artifacts_markdown_fence():
    text = "```markdown\n🎓 **H**\n```"
    assert _strip_agent_artifacts(text) == "🎓 **H**"


def test_strip_agent_artifacts_prefix():
    text = "Here's your polished version:\n\n🎓 **H**\n\nBody."
    out = _strip_agent_artifacts(text)
    assert out.startswith("🎓"), out


def test_strip_agent_artifacts_surrounding_quotes():
    text = '"🎓 **H** Body."'
    assert _strip_agent_artifacts(text) == "🎓 **H** Body."


def _make_polished(body: str = "Body text with [link](https://x/1).") -> str:
    return f"🎓 **Headline**\n\n{body}\n\n{FOOTER}"


def test_validate_invariants_all_valid():
    original = _make_polished()
    polished = _make_polished()
    assert _validate_invariants(original, polished, FOOTER) == []


def test_validate_invariants_lost_url():
    original = _make_polished("Body with [link](https://x/1) here.")
    polished = _make_polished("Body without the link here.")
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("lost URL" in v for v in violations), violations


def test_validate_invariants_link_count_dropped():
    original = f"🎓 **H**\n\n[a](http://x/1) and [b](http://y/2)\n\n{FOOTER}"
    polished = f"🎓 **H**\n\nBoth links removed\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("link count" in v or "lost URL" in v for v in violations), violations


def test_validate_invariants_missing_footer():
    original = _make_polished()
    polished = "🎓 **Headline**\n\nBody text with [link](https://x/1)."
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("footer" in v.lower() for v in violations), violations


def test_validate_invariants_length_over_900():
    original = _make_polished()
    polished = "🎓 **H**\n\n" + "word " * 300 + f"\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("over 900" in v or "length" in v.lower() for v in violations), violations


def test_validate_invariants_output_too_short():
    original = _make_polished()
    polished = "🎓 X"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("too short" in v or "100" in v for v in violations), violations


def test_validate_invariants_missing_headline_emoji():
    original = _make_polished()
    polished = f"**Headline**\n\nBody text with [link](https://x/1).\n\n{FOOTER}"
    violations = _validate_invariants(original, polished, FOOTER)
    assert any("emoji" in v.lower() for v in violations), violations


def test_validate_invariants_whitelisted_emojis_pass():
    for emoji in ["📰", "🎓", "💼", "🎉", "🏠", "💰", "⚡"]:
        body = f"Body text with [link](https://x/1)."
        polished = f"{emoji} **Headline**\n\n{body}\n\n{FOOTER}"
        assert _validate_invariants(polished, polished, FOOTER) == []


def test_critic_error_subclass_of_domain():
    from app.core.exceptions import DomainError

    assert issubclass(CriticError, DomainError)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_invariants.py -v`
Expected: FAIL — `app.channel.critic` does not exist.

- [ ] **Step 3: Create `app/channel/critic.py` with helpers**

Create `app/channel/critic.py`:

```python
"""Post critic: polish pass that removes clichés while preserving facts/links/structure.

Invoked from `generate_post` after length-enforcement, before the image pipeline.
On any failure the pipeline keeps the original text (silent fallback).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.core.exceptions import DomainError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.db.models import Channel

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
    if len(text) >= 2 and text[0] in {'"', "'", "«", "“"} and text[-1] in {'"', "'", "»", "”"}:
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
        import unicodedata

        cat = unicodedata.category(first)
        if not cat.startswith("So"):
            violations.append(f"headline emoji missing (first char: {first!r})")

    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_critic_invariants.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/critic.py tests/unit/test_critic_invariants.py
git commit -m "feat(critic): invariant validation + link/artifact helpers"
```

---

## Task 5: Critic module — `polish_post` with retry

Adds the LLM call, the system prompt, and the retry-then-fail-loud-with-CriticError path.

**Files:**
- Modify: `app/channel/critic.py`
- Create: `tests/unit/test_critic_polish.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_critic_polish.py`:

```python
"""Tests for polish_post — happy path, retry, and CriticError on persistent failure."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.channel.critic import CriticError, polish_post

pytestmark = pytest.mark.asyncio

FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"

ORIGINAL = (
    "🎓 **Продлили дедлайн стипендии**\n\n"
    "ČVUT продлил приём заявок на [стипендию](https://cvut.cz/s) "
    "до 15 мая. Подать документы можно в деканате.\n\n" + FOOTER
)

POLISHED_OK = (
    "🎓 **Дедлайн стипендии ČVUT перенесли**\n\n"
    "ČVUT принимает заявки на [стипендию](https://cvut.cz/s) до 15 мая. "
    "Документы — в деканате.\n\n" + FOOTER
)

POLISHED_MISSING_FOOTER = (
    "🎓 **Дедлайн стипендии ČVUT перенесли**\n\n"
    "ČVUT принимает заявки на [стипендию](https://cvut.cz/s) до 15 мая."
)


def _fake_run_result(output: str):
    """Build an object shaped like a PydanticAI RunResult for our purposes."""
    return SimpleNamespace(output=output)


async def test_polish_post_success():
    fake_agent = SimpleNamespace(run=AsyncMock(return_value=_fake_run_result(POLISHED_OK)))
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        out = await polish_post(
            text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6"
        )
    assert out == POLISHED_OK
    assert fake_agent.run.await_count == 1


async def test_polish_post_retry_then_success():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),  # first call — violates footer
                _fake_run_result(POLISHED_OK),  # retry — ok
            ]
        )
    )
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        out = await polish_post(
            text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6"
        )
    assert out == POLISHED_OK
    assert fake_agent.run.await_count == 2


async def test_polish_post_fails_after_retry():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),
                _fake_run_result(POLISHED_MISSING_FOOTER),
            ]
        )
    )
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        with pytest.raises(CriticError) as exc_info:
            await polish_post(
                text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6"
            )
    assert "footer" in str(exc_info.value).lower()
    assert fake_agent.run.await_count == 2


async def test_polish_post_raises_on_llm_exception():
    fake_agent = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("openrouter 500")))
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        with pytest.raises(CriticError):
            await polish_post(
                text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6"
            )


async def test_polish_post_logs_usage_per_call():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),
                _fake_run_result(POLISHED_OK),
            ]
        )
    )
    extract_mock = AsyncMock(return_value=None)
    log_mock = AsyncMock()
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", side_effect=extract_mock),
        patch("app.channel.critic.log_usage", log_mock),
    ):
        await polish_post(
            text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6"
        )

    # Two calls → two extract attempts, one per operation value.
    operations = [call.args[2] for call in extract_mock.await_args_list]
    assert operations == ["critic", "critic_retry"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_polish.py -v`
Expected: FAIL — `polish_post`/`_create_critic_agent` missing.

- [ ] **Step 3: Extend `app/channel/critic.py` with prompt, agent, polish_post**

Append to `app/channel/critic.py`:

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage
from app.core.config import settings


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

    retry_prompt = (
        f"{_RETRY_HINT}"
        f"Previous violations: {', '.join(violations)}\n\n"
        f"Original post (rewrite this):\n{text}"
    )

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_critic_polish.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/channel/critic.py tests/unit/test_critic_polish.py
git commit -m "feat(critic): polish_post with retry and usage tracking"
```

---

## Task 6: `resolve_critic_enabled` helper

Adds the per-channel-override-then-global resolver.

**Files:**
- Modify: `app/channel/critic.py`
- Create: `tests/unit/test_critic_resolve.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_critic_resolve.py`:

```python
"""Tests for resolve_critic_enabled — per-channel-override-then-global."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.channel.critic import resolve_critic_enabled


def _mk_channel(critic_enabled):
    return SimpleNamespace(critic_enabled=critic_enabled)


def _mk_settings(global_enabled: bool):
    return SimpleNamespace(channel=SimpleNamespace(critic_enabled=global_enabled))


@pytest.mark.parametrize(
    "channel_val,global_val,expected",
    [
        (None, False, False),
        (None, True, True),
        (True, False, True),
        (True, True, True),
        (False, False, False),
        (False, True, False),
    ],
)
def test_resolve_critic_enabled_matrix(channel_val, global_val, expected):
    assert (
        resolve_critic_enabled(_mk_channel(channel_val), _mk_settings(global_val))
        is expected
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_critic_resolve.py -v`
Expected: FAIL — `resolve_critic_enabled` missing.

- [ ] **Step 3: Implement the helper**

Append to `app/channel/critic.py`:

```python
def resolve_critic_enabled(channel: "Channel", settings_obj: "Settings") -> bool:
    """Resolve the effective critic-enabled flag.

    Per-channel value wins when set (True/False). None falls back to
    `settings.channel.critic_enabled`.
    """
    if channel.critic_enabled is not None:
        return channel.critic_enabled
    return settings_obj.channel.critic_enabled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_critic_resolve.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/channel/critic.py tests/unit/test_critic_resolve.py
git commit -m "feat(critic): resolve_critic_enabled helper"
```

---

## Task 7: Integrate critic into `generate_post`

New kwargs on `generate_post()` and the actual call site between length-enforcement and the image pipeline.

**Files:**
- Modify: `app/channel/generator.py`
- Create: `tests/integration/test_generator_with_critic.py`

- [ ] **Step 1: Write failing tests**

Create `tests/integration/test_generator_with_critic.py`:

```python
"""Tests for critic integration inside generate_post."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channel.generator import generate_post
from app.channel.sources import ContentItem

pytestmark = pytest.mark.asyncio


FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"
RAW_TEXT = f"🎓 **Headline**\n\nBody with [link](https://x/1) text.\n\n{FOOTER}"
POLISHED_TEXT = f"🎓 **Tighter Headline**\n\nBody with [link](https://x/1) text.\n\n{FOOTER}"


def _fake_generation_result(text: str):
    from types import SimpleNamespace

    from app.channel.generator import GeneratedPost

    return SimpleNamespace(output=GeneratedPost(text=text))


@pytest.fixture
def _item() -> list[ContentItem]:
    return [
        ContentItem(
            source_url="https://rss/x",
            external_id="abc",
            title="Headline",
            body="Body",
            url="https://x/1",
        )
    ]


async def test_generate_post_applies_critic_when_enabled(_item):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch(
            "app.channel.critic.polish_post",
            new=AsyncMock(return_value=POLISHED_TEXT),
        ),
    ):
        out = await generate_post(
            _item,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == POLISHED_TEXT
    assert out.pre_critic_text == RAW_TEXT


async def test_generate_post_no_critic_when_disabled(_item):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch("app.channel.critic.polish_post", new=AsyncMock()) as polish_mock,
    ):
        out = await generate_post(
            _item,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=False,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
    polish_mock.assert_not_awaited()


async def test_generate_post_no_critic_when_model_empty(_item):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch("app.channel.critic.polish_post", new=AsyncMock()) as polish_mock,
    ):
        out = await generate_post(
            _item,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
    polish_mock.assert_not_awaited()


async def test_generate_post_silent_fallback_on_critic_error(_item):
    from app.channel.critic import CriticError

    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch(
            "app.channel.critic.polish_post",
            new=AsyncMock(side_effect=CriticError("nope")),
        ),
    ):
        out = await generate_post(
            _item,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/integration/test_generator_with_critic.py -v`
Expected: FAIL — `critic_enabled` unknown kwarg.

- [ ] **Step 3: Add kwargs and call site**

In `app/channel/generator.py`, update `generate_post` signature (around line 323-338) to add two kwargs at the end:

```python
async def generate_post(
    items: list[ContentItem],
    api_key: str,
    model: str,
    language: str = "Russian",
    feedback_context: str | None = None,
    footer: str = "",
    *,
    channel_name: str = "",
    channel_context: str = "",
    channel_id: int | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    vision_model: str = "",
    phash_threshold: int = 10,
    phash_lookback: int = 30,
    critic_enabled: bool = False,
    critic_model: str = "",
) -> GeneratedPost | None:
```

Insert the critic block **after** `enforce_footer_and_length` and the shorten-retry block (which ends around line 398), **before** the image pipeline. The exact insertion point is right after the final `post.text = enforce_footer_and_length(post.text, footer, max_length=900)` inside the `if len(post.text) > 900` block. To keep the critic unconditional of the length retry, place it after the whole `if len(post.text) > 900:` block closes and before `# Resolve images: ...`. Concretely:

```python
        # Critic polish pass — best-effort. Silent fallback on failure.
        if critic_enabled and critic_model:
            try:
                from app.channel.critic import CriticError, polish_post

                original_text = post.text
                polished = await polish_post(
                    text=original_text,
                    footer=footer,
                    api_key=api_key,
                    model=critic_model,
                )
                post.pre_critic_text = original_text
                post.text = polished
                logger.info(
                    "critic_applied",
                    orig_len=len(original_text),
                    new_len=len(polished),
                )
            except CriticError as exc:
                logger.warning("critic_failed_fallback", reason=str(exc))
            except Exception:
                logger.exception("critic_unexpected_error")

        # Resolve images: new pipeline — filter, score, dedup, compose.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/integration/test_generator_with_critic.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/channel/generator.py tests/integration/test_generator_with_critic.py
git commit -m "feat(critic): wire polish_post into generate_post"
```

---

## Task 8: Workflow wiring + persist `pre_critic_text`

Resolves flags inside the Burr `generate_post` action and passes them to the generator. Also updates `create_review_post` to persist `pre_critic_text` on the `ChannelPost` row.

**Files:**
- Modify: `app/channel/workflow.py`
- Modify: `app/channel/review/service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_workflow_critic_wiring.py`:

```python
"""Tests that workflow.generate_post resolves and passes critic flags."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.channel.workflow import generate_post as wf_generate

pytestmark = pytest.mark.asyncio


class _Channel(SimpleNamespace):
    pass


async def _make_state():
    channel = _Channel(
        id=1,
        telegram_id=-100,
        name="X",
        language="ru",
        footer="——\n🔗 **Konnekt** | @konnekt_channel",
        footer_template=None,
        username="konnekt_channel",
        discovery_query="",
        critic_enabled=True,  # per-channel override
    )
    config = SimpleNamespace(
        generation_model="gen-model",
        vision_model="vis-model",
        image_phash_threshold=10,
        image_phash_lookback_posts=30,
        screening_model="sc",
        http_timeout=30,
        temperature=0.3,
        embedding_model="emb",
        semantic_dedup_threshold=0.9,
        dedup_lookback_days=30,
        dedup_query_snippet_chars=200,
        critic_enabled=False,  # global — ignored because channel is True
        critic_model="anthropic/claude-sonnet-4-6",
    )

    return {
        "relevant_items": [
            SimpleNamespace(title="T", body="B", url="https://x/1", source_url="https://rss", external_id="e")
        ],
        "api_key": "k",
        "config": config,
        "channel": channel,
        "channel_id": 1,
        "session_maker": AsyncMock(),
    }


async def test_workflow_generate_passes_critic_flags():
    state = await _make_state()

    from types import SimpleNamespace as SN

    fake_state = SN(
        __getitem__=lambda self, k: state[k],
        update=lambda **kw: SN(__getitem__=lambda self, k: {**state, **kw}.get(k)),
    )
    # Use a simple dict-based stub instead of the Burr State object.
    class _State(dict):
        def update(self, **kw):
            new = _State(self)
            new.update_raw(kw)
            return new

        def update_raw(self, kw):
            for k, v in kw.items():
                dict.__setitem__(self, k, v)

    s = _State(state)

    captured: dict = {}

    async def fake_generate(items, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="🎓 **H**\n\nB [l](https://x/1)\n\n" + state["channel"].footer,
            pre_critic_text=None,
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
            model_dump=lambda: {"text": "x"},
        )

    async def fake_find_nearest_posts(*args, **kwargs):
        return []

    async def fake_feedback(**kwargs):
        return None

    with (
        patch("app.channel.generator.generate_post", new=fake_generate),
        patch("app.channel.semantic_dedup.find_nearest_posts", new=fake_find_nearest_posts),
        patch("app.channel.feedback.get_feedback_summary", new=fake_feedback),
    ):
        await wf_generate(s)

    assert captured["critic_enabled"] is True
    assert captured["critic_model"] == "anthropic/claude-sonnet-4-6"


async def test_workflow_generate_channel_none_uses_global():
    state = await _make_state()
    state["channel"].critic_enabled = None  # fall back to global
    state["config"].critic_enabled = True

    class _State(dict):
        def update(self, **kw):
            new = _State(self)
            for k, v in kw.items():
                dict.__setitem__(new, k, v)
            return new

    s = _State(state)

    captured: dict = {}

    async def fake_generate(items, **kwargs):
        captured.update(kwargs)
        from types import SimpleNamespace as SN

        return SN(
            text="🎓 **H**\n\n\n\n" + state["channel"].footer,
            pre_critic_text=None,
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
            model_dump=lambda: {"text": "x"},
        )

    async def fake_find(*args, **kwargs):
        return []

    async def fake_feedback(**kwargs):
        return None

    with (
        patch("app.channel.generator.generate_post", new=fake_generate),
        patch("app.channel.semantic_dedup.find_nearest_posts", new=fake_find),
        patch("app.channel.feedback.get_feedback_summary", new=fake_feedback),
    ):
        await wf_generate(s)

    assert captured["critic_enabled"] is True
```

For `create_review_post` persistence, add a test in the same file:

```python
async def test_create_review_post_persists_pre_critic_text(session_maker):
    from sqlalchemy import select

    from app.channel.generator import GeneratedPost
    from app.channel.review.service import create_review_post
    from app.channel.sources import ContentItem
    from app.db.models import ChannelPost

    post = GeneratedPost(
        text="🎓 **H**\n\nB [l](https://x/1)\n\n——\n🔗 **K** | @c",
        pre_critic_text="🎓 **Original**\n\nOrig body\n\n——\n🔗 **K** | @c",
    )
    item = ContentItem(
        source_url="https://rss",
        external_id="e1",
        title="T",
        body="B",
        url="https://x/1",
    )
    async with session_maker() as session:
        cp = await create_review_post(
            channel_id=-100,
            post=post,
            source_items=[item],
            review_chat_id=-200,
            session=session,
        )
        await session.commit()
    assert cp is not None
    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == cp.id))).scalar_one()
    assert row.pre_critic_text.startswith("🎓 **Original**")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_workflow_critic_wiring.py -v`
Expected: FAIL — `create_review_post` ignores `pre_critic_text`; workflow doesn't pass kwargs.

- [ ] **Step 3: Patch `app/channel/workflow.py::generate_post`**

In `app/channel/workflow.py`, modify the `_generate(...)` call (around line 348) to resolve and pass the critic flags. Add the resolution just above the `_generate` call:

```python
    from app.channel.critic import resolve_critic_enabled
    from app.core.config import settings as _settings

    critic_enabled = resolve_critic_enabled(channel, _settings)
    critic_model = config.critic_model

    try:
        post = await _generate(
            relevant[:1],
            api_key=api_key,
            model=config.generation_model,
            language=language,
            feedback_context=feedback_context,
            footer=footer,
            channel_name=channel.name,
            channel_context=channel_context,
            channel_id=channel_id,
            session_maker=session_maker,
            vision_model=config.vision_model,
            phash_threshold=config.image_phash_threshold,
            phash_lookback=config.image_phash_lookback_posts,
            critic_enabled=critic_enabled,
            critic_model=critic_model,
        )
```

- [ ] **Step 4: Patch `create_review_post` to persist `pre_critic_text`**

In `app/channel/review/service.py`, update the `ChannelPost(...)` constructor call inside `create_review_post` (around line 135-146) to include `pre_critic_text`:

```python
    db_post = ChannelPost(
        channel_id=channel_id,
        external_id=ext_id,
        title=source_items[0].title[:REVIEW_TITLE_MAX_CHARS] if source_items else "Generated post",
        post_text=post.text,
        image_url=post.image_url,
        image_urls=post.image_urls or None,
        image_candidates=post.image_candidates,
        image_phashes=post.image_phashes or None,
        source_items=source_data,
        review_chat_id=int(review_chat_id) if review_chat_id else 0,
        pre_critic_text=post.pre_critic_text,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_workflow_critic_wiring.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/channel/workflow.py app/channel/review/service.py tests/unit/test_workflow_critic_wiring.py
git commit -m "feat(critic): resolve flags in workflow + persist pre_critic_text"
```

---

## Task 9: Review regen path wiring

The review service `regen_post_text` path calls `generate_post` again to produce a new draft. Thread critic flags through and copy `pre_critic_text` onto the persisted row.

**Files:**
- Modify: `app/channel/review/service.py` (regen path around line 482-506)

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_workflow_critic_wiring.py`:

```python
async def test_regen_post_text_threads_critic_and_persists(session_maker, monkeypatch):
    """regen_post_text must pass critic flags to generate_post and save pre_critic_text."""
    from app.channel.review.service import regen_post_text
    from app.core.enums import PostStatus
    from app.db.models import Channel, ChannelPost

    async with session_maker() as session:
        ch = Channel(
            telegram_id=-100,
            name="X",
            username="konnekt_channel",
            footer_template="——\n🔗 **K** | @c",
            critic_enabled=True,
        )
        session.add(ch)
        await session.flush()
        p = ChannelPost(
            channel_id=ch.telegram_id,
            external_id="e",
            title="t",
            post_text="old",
            status=PostStatus.DRAFT,
            source_items=[
                {"title": "T", "url": "https://x/1", "source_url": "https://rss", "external_id": "e"}
            ],
        )
        session.add(p)
        await session.commit()
        pid = p.id

    captured_kwargs: dict = {}

    async def fake_generate(items, **kwargs):
        from types import SimpleNamespace as SN

        captured_kwargs.update(kwargs)
        return SN(
            text="🎓 **New**\n\nBody [l](https://x/1)\n\n——\n🔗 **K** | @c",
            pre_critic_text="🎓 **Original**\n\nBody [l](https://x/1)\n\n——\n🔗 **K** | @c",
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
        )

    # The regen path uses `from app.channel.generator import generate_post`
    # (local import inside regen_post_text). Patch at the module source so the
    # subsequent local import binds to the fake.
    monkeypatch.setattr("app.channel.generator.generate_post", fake_generate)

    msg, post = await regen_post_text(
        session_maker=session_maker,
        post_id=pid,
        api_key="k",
        model="gen-m",
        language="Russian",
        footer="——\n🔗 **K** | @c",
    )
    assert post is not None
    assert captured_kwargs.get("critic_enabled") is True
    assert captured_kwargs.get("critic_model") == "anthropic/claude-sonnet-4-6"

    from sqlalchemy import select

    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
    assert row.pre_critic_text.startswith("🎓 **Original**")
```

Note: the test assumes `regen_post_text` exposes a signature compatible with these kwargs. Before running, inspect the existing signature and adjust test kwargs to match it exactly. The test is a **spec** — implementation follows.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_workflow_critic_wiring.py::test_regen_post_text_threads_critic_and_persists -v`
Expected: FAIL — either wrong signature or `pre_critic_text` not persisted.

- [ ] **Step 3: Patch the regen path**

In `app/channel/review/service.py` (around line 480-506), change the regen call site to resolve + pass critic flags and persist `pre_critic_text`:

```python
        from app.channel.critic import resolve_critic_enabled
        from app.core.config import settings

        # `post.channel_id` is the telegram id of the channel. Load the Channel row
        # to resolve the per-channel override. If not found, fall back to global.
        from sqlalchemy import select

        from app.db.models import Channel

        ch_row = (
            await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
        ).scalar_one_or_none()
        if ch_row is not None:
            critic_enabled = resolve_critic_enabled(ch_row, settings)
        else:
            critic_enabled = settings.channel.critic_enabled
        critic_model = settings.channel.critic_model

        new_post = await generate_post(
            items,
            api_key=api_key,
            model=model,
            language=language,
            footer=footer,
            channel_id=post.channel_id,
            session_maker=session_maker,
            vision_model=settings.channel.vision_model,
            phash_threshold=settings.channel.image_phash_threshold,
            phash_lookback=settings.channel.image_phash_lookback_posts,
            critic_enabled=critic_enabled,
            critic_model=critic_model,
        )
        if not new_post:
            return "Regeneration failed.", None

        post.update_text(new_post.text)
        post.pre_critic_text = new_post.pre_critic_text
        # Also refresh image fields from the new pipeline run — otherwise the
        # post's text and image pool diverge (old images stay attached to new text).
        post.image_url = new_post.image_url
        post.image_urls = new_post.image_urls or None
        post.image_candidates = new_post.image_candidates
        post.image_phashes = new_post.image_phashes or None
        await session.commit()
```

(If the existing code already imports `settings` once above, reuse that import rather than re-importing; otherwise this snippet works standalone.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_workflow_critic_wiring.py -v`
Expected: all prior tests + new regen test pass.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/service.py tests/unit/test_workflow_critic_wiring.py
git commit -m "feat(critic): thread flags + persist pre_critic_text on regen path"
```

---

## Task 10: Assistant bot `set_channel_critic` tool

User-facing control: flip per-channel critic override without touching SQL. Mirrors `edit_channel` but narrower (one field, accepts None).

**Files:**
- Modify: `app/assistant/tools/channel/channels.py`
- Create: `tests/unit/test_assistant_set_channel_critic.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_assistant_set_channel_critic.py`:

```python
"""Tests for the set_channel_critic assistant tool."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models import Channel

pytestmark = pytest.mark.asyncio


class _Recorder:
    """Capture PydanticAI `@agent.tool` registrations so tests can call them."""

    def __init__(self):
        self.tools: dict = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


async def test_set_channel_critic_enables(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-123, name="X")
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-123, enabled=True)
    assert "True" in msg or "включ" in msg.lower()

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -123))).scalar_one()
    assert row.critic_enabled is True


async def test_set_channel_critic_disables(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-124, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    await tool(ctx, telegram_id=-124, enabled=False)

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -124))).scalar_one()
    assert row.critic_enabled is False


async def test_set_channel_critic_resets_to_global(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-125, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-125, enabled=None)
    assert "global" in msg.lower() or "глобал" in msg.lower()

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -125))).scalar_one()
    assert row.critic_enabled is None


async def test_set_channel_critic_unknown_channel(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-9999, enabled=True)
    assert "не найден" in msg.lower() or "not found" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_assistant_set_channel_critic.py -v`
Expected: FAIL — `set_channel_critic` does not exist.

- [ ] **Step 3: Add the tool**

In `app/assistant/tools/channel/channels.py`, append a new `@agent.tool` inside `register_channels_tools`, right after `remove_channel`:

```python
    @agent.tool
    async def set_channel_critic(
        ctx: RunContext[AssistantDeps],
        telegram_id: int,
        enabled: bool | None,
    ) -> str:
        """Set per-channel critic override. enabled=True forces the critic on for
        this channel, False forces it off, None resets the override so the channel
        follows the global CHANNEL_CRITIC_ENABLED setting."""
        from sqlalchemy import select

        from app.core.config import settings
        from app.db.models import Channel

        async with ctx.deps.session_maker() as session:
            row = (
                await session.execute(select(Channel).where(Channel.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if row is None:
                return f"Канал {telegram_id} не найден."
            row.critic_enabled = enabled
            await session.commit()

        global_val = settings.channel.critic_enabled
        effective = enabled if enabled is not None else global_val
        if enabled is None:
            return (
                f"Канал {telegram_id}: override сброшен, теперь следует глобальной "
                f"настройке (effective={effective})."
            )
        return (
            f"Канал {telegram_id}: critic_enabled={enabled} "
            f"(global={global_val}, effective={effective})."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_assistant_set_channel_critic.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/assistant/tools/channel/channels.py tests/unit/test_assistant_set_channel_critic.py
git commit -m "feat(assistant): add set_channel_critic tool"
```

---

## Task 11: Full-suite verification

Run the whole test suite, linter, and type checker to catch regressions.

**Files:** none new; verification only.

- [ ] **Step 1: Run the full pytest suite**

Run: `uv run -m pytest -x`
Expected: all tests pass.

- [ ] **Step 2: Run ruff**

Run: `uv run -m ruff check app tests && uv run -m ruff format --check app tests`
Expected: no issues. If formatting failures, run `uv run -m ruff format app tests` and amend the most recent commit (or add a small follow-up commit if the history has already been pushed).

- [ ] **Step 3: Run the type checker**

Run: `uv run -m ty check app tests`
Expected: no new errors attributable to this work. Pre-existing errors outside this plan's files are out of scope.

- [ ] **Step 4: Smoke-check migrations**

Run: `uv run alembic upgrade head`
Expected: clean apply (no drift).

- [ ] **Step 5: Final commit (if any fixes were applied)**

```bash
git add -A
git commit -m "chore(critic): final lint + format fixes"
```

Only create this commit if steps 2 or 3 applied fixes.

---

## Verification summary

After Task 11:

- New module `app/channel/critic.py` with public surface `CriticError`, `polish_post`, `resolve_critic_enabled`, and private helpers covered by unit tests.
- `generate_post` accepts `critic_enabled` + `critic_model` kwargs, invokes the critic after length-enforcement, stores the original text in `pre_critic_text` on success, and silently falls back on `CriticError`.
- `channels.critic_enabled` (nullable bool) + `channel_posts.pre_critic_text` (nullable text) migrated and persisted end-to-end (workflow creation path and review regen path).
- Global env switches: `CHANNEL_CRITIC_ENABLED` (default False), `CHANNEL_CRITIC_MODEL` (default `anthropic/claude-sonnet-4-6`).
- Assistant bot tool `set_channel_critic(telegram_id, enabled)` for per-channel overrides.
- Default state after merge: global off, no channel overrides set → nothing runs until explicitly enabled.

## Rollout (post-merge, manual)

1. Deploy. Critic disabled globally — no behavior change.
2. Via assistant bot: `set_channel_critic(telegram_id=<dev>, enabled=True)` for `@test908070`.
3. Observe 20–30 posts; sanity-check tone, fact preservation, fallback rate via `critic_failed_fallback` log volume.
4. If clean, flip env `CHANNEL_CRITIC_ENABLED=true`; all channels inherit.
5. If a specific channel misbehaves later: `set_channel_critic(telegram_id=X, enabled=False)` — no redeploy.
