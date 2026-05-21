# Sponsored Ads v0 — Rate Card Funnel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect ad-spam in managed chats, let a moderator remove it privately (clearing cross-chat duplicates), and redirect the would-be advertiser to an external pricing article via a bot `/ads` command.

**Architecture:** A new `app/sponsored_ads/` feature module holds pure logic (text normalization, lead persistence, rate-card rendering, cross-chat cleanup, advertiser outreach, moderator-alert building, decision orchestration). Thin aiogram handlers in `app/presentation/telegram/` adapt Telegram callbacks/commands to that logic. `HistoryMiddleware` triggers a moderator alert when the existing ad-detector fires. The previous over-scoped `SponsoredAdRequest` skeleton is removed first.

**Tech Stack:** Python 3.12, aiogram 3.x, SQLAlchemy 2.x async, Alembic, Pydantic Settings, pytest (`asyncio_mode=auto`), `uv`.

**Spec:** `docs/superpowers/specs/2026-05-21-sponsored-ads-rate-card-design.md`

**Branch:** Work continues on `docs/sponsored-ads-product` (the live feature branch).

---

## File Structure

**Removed (Task 1):**
- `app/sponsored_ads/domain.py`, `app/sponsored_ads/service.py`
- `app/db/repositories/sponsored_ads.py`
- `SponsoredAdRequest` in `app/db/models.py`
- `alembic/versions/c3d4e5f6a7b8_add_sponsored_ad_requests.py`
- `tests/unit/test_sponsored_ads_domain.py`, `test_sponsored_ads_repository.py`, `test_sponsored_ads_service.py`

**Created:**
- `app/sponsored_ads/text.py` — `normalize_text`
- `app/sponsored_ads/leads.py` — `AdLeadRepository`
- `app/sponsored_ads/rate_card.py` — message rendering
- `app/sponsored_ads/cleanup.py` — `delete_ad_duplicates`
- `app/sponsored_ads/outreach.py` — `reach_advertiser`
- `app/sponsored_ads/review.py` — moderator-alert detection + building
- `app/sponsored_ads/decisions.py` — `apply_ad_decision`
- `app/presentation/telegram/handlers/ad_review.py` — moderator callback handler
- `alembic/versions/a1b2c3d4e5f6_add_ad_leads.py` — `ad_leads` migration

**Modified:**
- `app/core/config.py` — `SponsoredAdsSettings`
- `app/db/models.py` — `AdLead` model
- `app/presentation/telegram/utils/callback_data.py` — `AdReviewAction`
- `app/presentation/telegram/handlers/start.py` — `/ads`, deep links, greeting line
- `app/presentation/telegram/handlers/__init__.py` — register `ad_review_router`
- `app/presentation/telegram/middlewares/history.py` — trigger moderator alert
- `.env.example`, `docs/product/sponsored-ads.md`, `docs/domain/sponsored-ads.md`

---

## Task 1: Remove the old sponsored-ads skeleton

**Files:**
- Delete: `app/sponsored_ads/domain.py`, `app/sponsored_ads/service.py`
- Delete: `app/db/repositories/sponsored_ads.py`
- Delete: `alembic/versions/c3d4e5f6a7b8_add_sponsored_ad_requests.py`
- Delete: `tests/unit/test_sponsored_ads_domain.py`, `tests/unit/test_sponsored_ads_repository.py`, `tests/unit/test_sponsored_ads_service.py`
- Modify: `app/db/models.py` (remove import line 12 + the `SponsoredAdRequest` class)
- Modify: `app/db/repositories/__init__.py` (remove the two `sponsored_ads` exports)
- Modify: `app/sponsored_ads/__init__.py` (update docstring)

- [ ] **Step 1: Delete the obsolete files**

```bash
git rm app/sponsored_ads/domain.py app/sponsored_ads/service.py \
       app/db/repositories/sponsored_ads.py \
       alembic/versions/c3d4e5f6a7b8_add_sponsored_ad_requests.py \
       tests/unit/test_sponsored_ads_domain.py \
       tests/unit/test_sponsored_ads_repository.py \
       tests/unit/test_sponsored_ads_service.py
```

- [ ] **Step 2: Remove the `SponsoredAdRequest` model and its import from `app/db/models.py`**

Delete line 12 entirely:

```python
from app.sponsored_ads.domain import AdCategoryPolicy, AdRequestStatus
```

Delete the entire `SponsoredAdRequest` class (the `class SponsoredAdRequest(Base):` block, currently lines 722-781 — from `class SponsoredAdRequest` down to the end of its `__init__`).

- [ ] **Step 3: Remove the sponsored-ads exports from `app/db/repositories/__init__.py`**

Delete these two lines:

```python
from .sponsored_ads import SponsoredAdRequestRepository as SponsoredAdRequestRepository
from .sponsored_ads import get_sponsored_ad_request_repository as get_sponsored_ad_request_repository
```

- [ ] **Step 4: Update `app/sponsored_ads/__init__.py` docstring**

Replace the file's entire content with:

```python
"""Sponsored ads rate-card funnel."""
```

- [ ] **Step 5: Verify no stragglers reference the removed code**

Run: `grep -rn "SponsoredAdRequest\|sponsored_ads.domain\|sponsored_ads.service\|sponsored_ads import" app tests`
Expected: no matches. If any appear, remove or fix those references before continuing.

- [ ] **Step 6: Verify the migration head and the test suite**

Run: `uv run alembic heads`
Expected: `b2c3d4e5f6a7 (head)` — exactly one head.

Run: `uv run -m pytest tests/unit -q`
Expected: PASS (the three deleted test files are gone; nothing else references the removed code).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove over-scoped sponsored ads skeleton"
```

(The pre-commit hook runs ruff + ty; the commit fails if either fails — fix and re-commit.)

---

## Task 2: `SponsoredAdsSettings` configuration

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config_sponsored_ads.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config_sponsored_ads.py`:

```python
import pytest

from app.core.config import SponsoredAdsSettings


def test_sponsored_ads_settings_defaults() -> None:
    s = SponsoredAdsSettings()
    assert s.enabled is False
    assert s.moderator_chat_id == 0
    assert s.pricing_article_url == ""
    assert s.sales_contact == ""


def test_sponsored_ads_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONSORED_ADS_ENABLED", "true")
    monkeypatch.setenv("SPONSORED_ADS_MODERATOR_CHAT_ID", "-1009999")
    monkeypatch.setenv("SPONSORED_ADS_PRICING_ARTICLE_URL", "https://telegra.ph/ads")
    monkeypatch.setenv("SPONSORED_ADS_SALES_CONTACT", "@konnekt_ads")
    s = SponsoredAdsSettings()
    assert s.enabled is True
    assert s.moderator_chat_id == -1009999
    assert s.pricing_article_url == "https://telegra.ph/ads"
    assert s.sales_contact == "@konnekt_ads"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_config_sponsored_ads.py -v`
Expected: FAIL with `ImportError: cannot import name 'SponsoredAdsSettings'`.

- [ ] **Step 3: Add `SponsoredAdsSettings` to `app/core/config.py`**

Add this class immediately before the `class AppSettings(BaseSettings):` line:

```python
class SponsoredAdsSettings(BaseSettings):
    """Sponsored ads rate-card funnel configuration."""

    enabled: bool = Field(default=False, description="Whether the sponsored-ads rate-card funnel is active")
    moderator_chat_id: int = Field(
        default=0,
        description="Chat that receives ad-review alerts (0 disables alerts)",
    )
    pricing_article_url: str = Field(
        default="",
        description="External article (Telegraph/Notion) with pricing and the chat list",
    )
    sales_contact: str = Field(
        default="",
        description="@username shown in the rate card for ad-sales questions",
    )

    model_config = SettingsConfigDict(
        env_prefix="SPONSORED_ADS_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
```

- [ ] **Step 4: Compose it into `AppSettings`**

In the `class AppSettings(BaseSettings):` body, add this line directly after the `webapi: WebApiSettings = Field(default_factory=WebApiSettings)` line:

```python
    sponsored_ads: SponsoredAdsSettings = Field(default_factory=SponsoredAdsSettings)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_config_sponsored_ads.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Document the env vars in `.env.example`**

Append to the end of `.env.example`:

```bash

# Sponsored ads rate-card funnel
SPONSORED_ADS_ENABLED=false
SPONSORED_ADS_MODERATOR_CHAT_ID=0
SPONSORED_ADS_PRICING_ARTICLE_URL=
SPONSORED_ADS_SALES_CONTACT=
```

- [ ] **Step 7: Commit**

```bash
git add app/core/config.py .env.example tests/unit/test_config_sponsored_ads.py
git commit -m "feat: add SponsoredAdsSettings config"
```

---

## Task 3: `AdLead` model and migration

**Files:**
- Modify: `app/db/models.py`
- Create: `alembic/versions/a1b2c3d4e5f6_add_ad_leads.py`
- Test: `tests/unit/test_ad_lead_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ad_lead_model.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdLead


async def test_ad_lead_persists_with_defaults(session: AsyncSession) -> None:
    lead = AdLead(chat_id=-1001, user_id=555, snippet="buy now cheap")
    session.add(lead)
    await session.flush()

    assert lead.id is not None
    assert lead.reached_via == "failed"
    assert lead.created_at is not None
    assert lead.link_clicked_at is None
    assert lead.snippet == "buy now cheap"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_ad_lead_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'AdLead'`.

- [ ] **Step 3: Add the `AdLead` model to `app/db/models.py`**

Add this class immediately after the `SpamPing` class (after its `__init__` ends, around line 720):

```python
class AdLead(Base):
    """A would-be advertiser redirected to the paid-placement rate card.

    Created when a moderator removes a flagged ad via the `Удалить` action.
    Tracks how the advertiser was reached and whether they opened the
    rate-card smart link.
    """

    __tablename__ = "ad_leads"
    __table_args__ = (Index("ix_ad_leads_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    snippet: Mapped[str | None] = mapped_column(String, nullable=True)
    reached_via: Mapped[str] = mapped_column(String(8), default="failed")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now)
    link_clicked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    def __init__(
        self,
        *,
        chat_id: int,
        user_id: int,
        snippet: str | None = None,
        reached_via: str = "failed",
    ) -> None:
        self.chat_id = chat_id
        self.user_id = user_id
        self.snippet = snippet
        self.reached_via = reached_via
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_ad_lead_model.py -v`
Expected: PASS.

- [ ] **Step 5: Create the Alembic migration**

Create `alembic/versions/a1b2c3d4e5f6_add_ad_leads.py`:

```python
"""Add ad_leads table.

Tracks would-be advertisers redirected to the paid-placement rate card.

Revision ID: a1b2c3d4e5f6
Revises: b2c3d4e5f6a7
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_leads",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("snippet", sa.String, nullable=True),
        sa.Column("reached_via", sa.String(8), nullable=False, server_default="failed"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("link_clicked_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_ad_leads_created_at", "ad_leads", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ad_leads_created_at", table_name="ad_leads")
    op.drop_table("ad_leads")
```

- [ ] **Step 6: Verify the migration applies cleanly**

Run: `uv run alembic heads`
Expected: `a1b2c3d4e5f6 (head)` — exactly one head.

Run: `uv run alembic upgrade head`
Expected: applies `a1b2c3d4e5f6` with no error.

- [ ] **Step 7: Commit**

```bash
git add app/db/models.py alembic/versions/a1b2c3d4e5f6_add_ad_leads.py tests/unit/test_ad_lead_model.py
git commit -m "feat: add ad_leads table and AdLead model"
```

---

## Task 4: `normalize_text` helper

**Files:**
- Create: `app/sponsored_ads/text.py`
- Test: `tests/unit/test_sponsored_ads_text.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_text.py`:

```python
from app.sponsored_ads.text import normalize_text


def test_normalize_collapses_whitespace_and_casefolds() -> None:
    assert normalize_text("  Buy   NOW\n\nCheap ") == "buy now cheap"


def test_normalize_handles_none_and_empty() -> None:
    assert normalize_text(None) == ""
    assert normalize_text("   ") == ""


def test_normalize_identical_for_blast_copies() -> None:
    a = normalize_text("СРОЧНО продам айфон  @seller")
    b = normalize_text("срочно ПРОДАМ айфон @seller")
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_text.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.text'`.

- [ ] **Step 3: Create `app/sponsored_ads/text.py`**

```python
"""Text normalization shared by ad-review dedup and cross-chat cleanup."""

from __future__ import annotations


def normalize_text(text: str | None) -> str:
    """Return a comparison-friendly form: trimmed, whitespace-collapsed, casefolded."""
    if not text:
        return ""
    return " ".join(text.split()).casefold()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_text.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/text.py tests/unit/test_sponsored_ads_text.py
git commit -m "feat: add normalize_text helper for sponsored ads"
```

---

## Task 5: `AdLeadRepository`

**Files:**
- Create: `app/sponsored_ads/leads.py`
- Test: `tests/unit/test_sponsored_ads_leads.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_leads.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.sponsored_ads.leads import AdLeadRepository


async def test_create_lead_defaults(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet="ad text")
    assert lead.id is not None
    assert lead.reached_via == "failed"
    assert lead.link_clicked_at is None


async def test_set_reached_via(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)
    await repo.set_reached_via(lead.id, "dm")
    refreshed = await repo.get_by_id(lead.id)
    assert refreshed is not None
    assert refreshed.reached_via == "dm"


async def test_mark_clicked_sets_timestamp_once(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)

    assert await repo.mark_clicked(lead.id) is True
    first = await repo.get_by_id(lead.id)
    assert first is not None and first.link_clicked_at is not None
    first_ts = first.link_clicked_at

    assert await repo.mark_clicked(lead.id) is True
    second = await repo.get_by_id(lead.id)
    assert second is not None and second.link_clicked_at == first_ts  # not overwritten


async def test_mark_clicked_missing_lead(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    assert await repo.mark_clicked(999) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_leads.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.leads'`.

- [ ] **Step 3: Create `app/sponsored_ads/leads.py`**

```python
"""Persistence for ad_leads — the rate-card funnel tracking rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.time import utc_now
from app.db.models import AdLead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AdLeadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, lead_id: int) -> AdLead | None:
        result = await self.db.execute(select(AdLead).where(AdLead.id == lead_id))
        return result.scalars().first()

    async def create_lead(self, *, chat_id: int, user_id: int, snippet: str | None) -> AdLead:
        lead = AdLead(chat_id=chat_id, user_id=user_id, snippet=snippet)
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def set_reached_via(self, lead_id: int, reached_via: str) -> None:
        lead = await self.get_by_id(lead_id)
        if lead is None:
            return
        lead.reached_via = reached_via
        await self.db.commit()

    async def mark_clicked(self, lead_id: int) -> bool:
        """Stamp link_clicked_at if not already set. Returns True if a lead was found."""
        lead = await self.get_by_id(lead_id)
        if lead is None:
            return False
        if lead.link_clicked_at is None:
            lead.link_clicked_at = utc_now()
            await self.db.commit()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_leads.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/leads.py tests/unit/test_sponsored_ads_leads.py
git commit -m "feat: add AdLeadRepository"
```

---

## Task 6: Rate-card and outreach message rendering

**Files:**
- Create: `app/sponsored_ads/rate_card.py`
- Test: `tests/unit/test_sponsored_ads_rate_card.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_rate_card.py`:

```python
import pytest

from app.core.config import settings
from app.sponsored_ads.rate_card import (
    render_outreach_message,
    render_ping_message,
    render_rate_card,
)


def test_render_rate_card_includes_article_and_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "https://telegra.ph/ads")
    monkeypatch.setattr(settings.sponsored_ads, "sales_contact", "@konnekt_ads")
    text = render_rate_card()
    assert "https://telegra.ph/ads" in text
    assert "@konnekt_ads" in text


def test_render_rate_card_omits_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "")
    monkeypatch.setattr(settings.sponsored_ads, "sales_contact", "")
    text = render_rate_card()
    assert "Реклама" in text  # still renders a headline, no crash


def test_render_outreach_message_embeds_link() -> None:
    text = render_outreach_message("https://t.me/bot?start=adlead_5")
    assert "https://t.me/bot?start=adlead_5" in text


def test_render_ping_message_mentions_user_and_link() -> None:
    text = render_ping_message(777, "https://t.me/bot?start=adlead_5")
    assert "tg://user?id=777" in text
    assert "https://t.me/bot?start=adlead_5" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_rate_card.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.rate_card'`.

- [ ] **Step 3: Create `app/sponsored_ads/rate_card.py`**

```python
"""Rendering for the rate-card and advertiser-outreach messages (HTML)."""

from __future__ import annotations

from app.core.config import settings
from app.core.text import escape_html


def render_rate_card() -> str:
    """Public advertising info shown by /ads and the smart link."""
    cfg = settings.sponsored_ads
    lines = [
        "📢 <b>Реклама в наших чатах</b>",
        "",
        "Хотите разместить рекламу легально? Возможно платное размещение.",
    ]
    if cfg.pricing_article_url:
        lines.append(
            f'Цены, условия и список чатов: '
            f'<a href="{escape_html(cfg.pricing_article_url)}">подробнее тут</a>.'
        )
    if cfg.sales_contact:
        lines.append(f"По вопросам размещения: {escape_html(cfg.sales_contact)}")
    return "\n".join(lines)


def render_outreach_message(smart_link: str) -> str:
    """DM text sent to a would-be advertiser after their ad is removed."""
    return (
        "👋 Ваше сообщение выглядело как реклама и было удалено — "
        "здесь реклама запрещена.\n\n"
        f'Хотите разместить рекламу легально? '
        f'<a href="{escape_html(smart_link)}">Узнать про платное размещение</a>.'
    )


def render_ping_message(user_id: int, smart_link: str) -> str:
    """Public group ping used when the advertiser cannot be reached by DM."""
    mention = f'<a href="tg://user?id={user_id}">Пользователь</a>'
    return (
        f"{mention}, реклама в этом чате запрещена. "
        f'Хотите разместить легально? '
        f'<a href="{escape_html(smart_link)}">Узнать про платное размещение</a>.'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_rate_card.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/rate_card.py tests/unit/test_sponsored_ads_rate_card.py
git commit -m "feat: add rate-card and outreach message rendering"
```

---

## Task 7: Cross-chat duplicate cleanup

**Files:**
- Create: `app/sponsored_ads/cleanup.py`
- Test: `tests/unit/test_sponsored_ads_cleanup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_cleanup.py`:

```python
import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Message
from app.sponsored_ads.cleanup import delete_ad_duplicates

CHAT_A = -1001
CHAT_B = -1002
CHAT_C = -1003


class _RecordingBot:
    """Minimal bot stub recording delete_message calls."""

    def __init__(self, fail_on: set[tuple[int, int]] | None = None) -> None:
        self.deleted: list[tuple[int, int]] = []
        self._fail_on = fail_on or set()

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        if (chat_id, message_id) in self._fail_on:
            raise RuntimeError("message to delete not found")
        self.deleted.append((chat_id, message_id))
        return True


def _msg(chat_id: int, message_id: int, user_id: int, text: str, ts: datetime.datetime | None = None) -> Message:
    m = Message(chat_id=chat_id, user_id=user_id, message_id=message_id, message=text)
    if ts is not None:
        m.timestamp = ts
    return m


async def test_deletes_duplicates_across_chats(session: AsyncSession) -> None:
    spam = "Buy cheap iPhones @seller"
    session.add_all([
        _msg(CHAT_A, 11, 777, spam),
        _msg(CHAT_B, 22, 777, "  buy CHEAP   iphones @seller "),  # same after normalize
        _msg(CHAT_C, 33, 777, "totally different message"),
        _msg(CHAT_B, 99, 888, spam),  # different user — must not be touched
    ])
    await session.commit()
    bot = _RecordingBot()

    result = await delete_ad_duplicates(
        bot, session, user_id=777, origin_chat_id=CHAT_A, origin_message_id=11,
    )

    assert set(bot.deleted) == {(CHAT_A, 11), (CHAT_B, 22)}
    assert result.deleted == 2
    assert result.origin_text == spam


async def test_ignores_messages_outside_window(session: AsyncSession) -> None:
    spam = "same spam text"
    old = utc_now() - datetime.timedelta(hours=48)
    session.add_all([
        _msg(CHAT_A, 11, 777, spam),
        _msg(CHAT_B, 22, 777, spam, ts=old),
    ])
    await session.commit()
    bot = _RecordingBot()

    result = await delete_ad_duplicates(
        bot, session, user_id=777, origin_chat_id=CHAT_A, origin_message_id=11,
    )

    assert set(bot.deleted) == {(CHAT_A, 11)}
    assert result.deleted == 1


async def test_origin_deleted_even_without_messages_row(session: AsyncSession) -> None:
    bot = _RecordingBot()
    result = await delete_ad_duplicates(
        bot, session, user_id=777, origin_chat_id=CHAT_A, origin_message_id=11,
    )
    assert bot.deleted == [(CHAT_A, 11)]
    assert result.deleted == 1
    assert result.origin_text is None


async def test_delete_failure_is_skipped(session: AsyncSession) -> None:
    spam = "spam"
    session.add_all([
        _msg(CHAT_A, 11, 777, spam),
        _msg(CHAT_B, 22, 777, spam),
    ])
    await session.commit()
    bot = _RecordingBot(fail_on={(CHAT_B, 22)})

    result = await delete_ad_duplicates(
        bot, session, user_id=777, origin_chat_id=CHAT_A, origin_message_id=11,
    )
    assert result.deleted == 1  # CHAT_B/22 failed, counted out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_cleanup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.cleanup'`.

- [ ] **Step 3: Create `app/sponsored_ads/cleanup.py`**

```python
"""Cross-chat cleanup of an advertiser's duplicate ad messages."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Message
from app.sponsored_ads.text import normalize_text

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.cleanup")


@dataclass(frozen=True)
class CleanupResult:
    deleted: int
    origin_text: str | None


async def delete_ad_duplicates(
    bot: Bot,
    db: AsyncSession,
    *,
    user_id: int,
    origin_chat_id: int,
    origin_message_id: int,
    window_hours: int = 24,
) -> CleanupResult:
    """Delete the origin ad and every identical message from the same user.

    "Identical" = same normalized text, posted within `window_hours`, in any
    chat. The origin pair is always attempted, even if its `messages` row is
    missing. Per-message delete failures are logged and skipped.
    """
    cutoff = utc_now() - datetime.timedelta(hours=window_hours)

    origin_row = (
        await db.execute(
            select(Message).where(
                Message.chat_id == origin_chat_id,
                Message.message_id == origin_message_id,
            )
        )
    ).scalars().first()
    origin_text = origin_row.message if origin_row else None

    pairs: set[tuple[int, int]] = {(origin_chat_id, origin_message_id)}
    if origin_text:
        target = normalize_text(origin_text)
        rows = (
            await db.execute(
                select(Message).where(
                    Message.user_id == user_id,
                    Message.timestamp >= cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            if row.message and normalize_text(row.message) == target:
                pairs.add((row.chat_id, row.message_id))

    deleted = 0
    for chat_id, message_id in pairs:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted += 1
        except Exception as err:
            logger.warning(
                "ad_duplicate_delete_failed",
                error=str(err),
                chat_id=chat_id,
                message_id=message_id,
            )
    return CleanupResult(deleted=deleted, origin_text=origin_text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_cleanup.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/cleanup.py tests/unit/test_sponsored_ads_cleanup.py
git commit -m "feat: add cross-chat ad duplicate cleanup"
```

---

## Task 8: Advertiser outreach (DM with ping fallback)

**Files:**
- Create: `app/sponsored_ads/outreach.py`
- Test: `tests/unit/test_sponsored_ads_outreach.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_outreach.py`:

```python
from types import SimpleNamespace

from app.sponsored_ads.outreach import reach_advertiser

USER_ID = 777
ORIGIN_CHAT = -1001


class _StubBot:
    """Bot stub: positive chat_id == DM to user, negative == group ping."""

    def __init__(self, *, dm_ok: bool = True, ping_ok: bool = True) -> None:
        self._dm_ok = dm_ok
        self._ping_ok = ping_ok
        self.sent: list[tuple[int, str]] = []

    async def me(self) -> SimpleNamespace:
        return SimpleNamespace(username="konnekt_moder_bot")

    async def send_message(self, chat_id: int, text: str, disable_web_page_preview: bool = False) -> SimpleNamespace:
        if chat_id > 0 and not self._dm_ok:
            raise RuntimeError("bot can't initiate conversation with a user")
        if chat_id < 0 and not self._ping_ok:
            raise RuntimeError("chat send failed")
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=1)


async def test_reach_advertiser_dm_success() -> None:
    bot = _StubBot(dm_ok=True)
    result = await reach_advertiser(bot, user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result == "dm"
    assert bot.sent[0][0] == USER_ID
    assert "adlead_5" in bot.sent[0][1]


async def test_reach_advertiser_falls_back_to_ping() -> None:
    bot = _StubBot(dm_ok=False, ping_ok=True)
    result = await reach_advertiser(bot, user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result == "ping"
    assert bot.sent[0][0] == ORIGIN_CHAT
    assert "adlead_5" in bot.sent[0][1]


async def test_reach_advertiser_failed_when_both_fail() -> None:
    bot = _StubBot(dm_ok=False, ping_ok=False)
    result = await reach_advertiser(bot, user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result == "failed"
    assert bot.sent == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_outreach.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.outreach'`.

- [ ] **Step 3: Create `app/sponsored_ads/outreach.py`**

```python
"""Reach a would-be advertiser after their ad is removed: DM, else public ping."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.sponsored_ads.rate_card import render_outreach_message, render_ping_message

if TYPE_CHECKING:
    from aiogram import Bot

logger = get_logger("sponsored_ads.outreach")


async def build_smart_link(bot: Bot, lead_id: int) -> str:
    """Deep link that opens the bot on the rate card and marks the lead clicked."""
    me = await bot.me()
    return f"https://t.me/{me.username}?start=adlead_{lead_id}"


async def reach_advertiser(
    bot: Bot,
    *,
    user_id: int,
    origin_chat_id: int,
    lead_id: int,
) -> str:
    """Try a DM first; on any failure fall back to a public ping.

    Returns the channel actually used: "dm", "ping", or "failed". The DM
    attempt is caught broadly on purpose — a bot cannot DM a user who never
    started it, and any such failure should fall back to the public ping.
    """
    smart_link = await build_smart_link(bot, lead_id)

    try:
        await bot.send_message(
            user_id,
            render_outreach_message(smart_link),
            disable_web_page_preview=True,
        )
        return "dm"
    except Exception as err:
        logger.info("ad_outreach_dm_unavailable", user_id=user_id, error=str(err))

    try:
        await bot.send_message(
            origin_chat_id,
            render_ping_message(user_id, smart_link),
            disable_web_page_preview=True,
        )
        return "ping"
    except Exception as err:
        logger.warning("ad_outreach_ping_failed", chat_id=origin_chat_id, error=str(err))
        return "failed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_outreach.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/outreach.py tests/unit/test_sponsored_ads_outreach.py
git commit -m "feat: add advertiser outreach with ping fallback"
```

---

## Task 9: Moderator-alert detection and building

**Files:**
- Modify: `app/presentation/telegram/utils/callback_data.py`
- Create: `app/sponsored_ads/review.py`
- Test: `tests/unit/test_sponsored_ads_review.py`

- [ ] **Step 1: Add the `AdReviewAction` callback factory**

Append to `app/presentation/telegram/utils/callback_data.py`:

```python


# ── Sponsored-ads moderator review ──


class AdReviewAction(CallbackData, prefix="adrv"):
    """A moderator's decision on a flagged ad message."""

    action: str  # skip, delete, ban
    chat_id: int
    message_id: int
    user_id: int
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_sponsored_ads_review.py`:

```python
import datetime

import pytest
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Message
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads import review


def _user(user_id: int = 777) -> types.User:
    return types.User(id=user_id, is_bot=False, first_name="Ad")


def _message(text: str = "buy now") -> types.Message:
    return types.Message(
        message_id=11,
        date=datetime.datetime(2026, 5, 21),
        chat=types.Chat(id=-1001, type="supergroup", title="Prague Chat"),
        from_user=_user(),
        text=text,
    )


class _StubBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object = None, disable_web_page_preview: bool = False
    ) -> None:
        self.messages.append((chat_id, text))


async def test_should_send_alert_true_for_first_occurrence(session: AsyncSession) -> None:
    session.add(Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"))
    await session.commit()
    assert await review.should_send_alert(session, user_id=777, text="buy now") is True


async def test_should_send_alert_false_for_repeat_blast(session: AsyncSession) -> None:
    session.add_all([
        Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"),
        Message(chat_id=-1002, user_id=777, message_id=22, message="BUY  now"),
    ])
    await session.commit()
    assert await review.should_send_alert(session, user_id=777, text="buy now") is False


async def test_should_send_alert_false_for_empty_text(session: AsyncSession) -> None:
    assert await review.should_send_alert(session, user_id=777, text=None) is False


def test_build_alert_text_contains_chat_user_and_snippet() -> None:
    text = review.build_alert_text(chat_title="Prague Chat", user=_user(), snippet="Buy cheap stuff")
    assert "Prague Chat" in text
    assert "777" in text
    assert "Buy cheap stuff" in text


def test_build_alert_keyboard_has_three_actions() -> None:
    kb = review.build_alert_keyboard(chat_id=-1001, message_id=11, user_id=777)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    actions = {AdReviewAction.unpack(cb).action for cb in callbacks}
    assert actions == {"skip", "delete", "ban"}


async def test_notify_moderators_sends_alert(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "enabled", True)
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", -100999)
    session.add(Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"))
    await session.commit()
    bot = _StubBot()

    await review.notify_moderators(bot, session, _message())

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == -100999


async def test_notify_moderators_disabled_is_noop(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "enabled", False)
    bot = _StubBot()
    await review.notify_moderators(bot, session, _message())
    assert bot.messages == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.review'`.

- [ ] **Step 4: Create `app/sponsored_ads/review.py`**

```python
"""Detect ad blasts and alert moderators with action buttons."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import escape_html
from app.core.time import utc_now
from app.db.models import Message
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads.text import normalize_text

if TYPE_CHECKING:
    from aiogram import Bot, types
    from aiogram.types import InlineKeyboardMarkup
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.review")

_SNIPPET_CHARS = 300


async def should_send_alert(
    db: AsyncSession,
    *,
    user_id: int,
    text: str | None,
    window_hours: int = 24,
) -> bool:
    """False when this (user, text) blast was already alerted within the window.

    The current message is already saved in `messages` by the time this runs,
    so exactly one match is the current message itself; two or more means an
    earlier copy exists and an alert was already sent for it.
    """
    if not text:
        return False
    target = normalize_text(text)
    cutoff = utc_now() - datetime.timedelta(hours=window_hours)
    rows = (
        await db.execute(
            select(Message.message).where(
                Message.user_id == user_id,
                Message.timestamp >= cutoff,
            )
        )
    ).scalars().all()
    matches = sum(1 for m in rows if m and normalize_text(m) == target)
    return matches <= 1


def build_alert_text(*, chat_title: str | None, user: types.User, snippet: str) -> str:
    """HTML alert body shown to moderators."""
    mention = user.mention_html()
    chat = escape_html(chat_title or "—")
    body = escape_html(snippet[:_SNIPPET_CHARS])
    return (
        "📢 <b>Похоже на рекламу</b>\n"
        f"Чат: {chat}\n"
        f"Автор: {mention} (<code>{user.id}</code>)\n\n"
        f"<blockquote>{body}</blockquote>"
    )


def build_alert_keyboard(*, chat_id: int, message_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Three-button keyboard: skip / delete / ban."""
    builder = InlineKeyboardBuilder()
    for text, action in (("⏭ Пропустить", "skip"), ("🗑 Удалить", "delete"), ("🚫 Бан", "ban")):
        builder.button(
            text=text,
            callback_data=AdReviewAction(
                action=action, chat_id=chat_id, message_id=message_id, user_id=user_id
            ),
        )
    builder.adjust(3)
    return builder.as_markup()


async def notify_moderators(bot: Bot, db: AsyncSession, message: types.Message) -> None:
    """Send a moderator alert for a freshly-detected ad message.

    No-op when the feature is disabled, no moderator chat is configured, the
    message has no author, or this blast was already alerted.
    """
    cfg = settings.sponsored_ads
    if not cfg.enabled or not cfg.moderator_chat_id:
        return
    user = message.from_user
    if user is None:
        return
    text = message.text or message.caption
    if not await should_send_alert(db, user_id=user.id, text=text):
        return

    alert = build_alert_text(chat_title=message.chat.title, user=user, snippet=text or "")
    keyboard = build_alert_keyboard(
        chat_id=message.chat.id,
        message_id=message.message_id,
        user_id=user.id,
    )
    try:
        await bot.send_message(
            cfg.moderator_chat_id,
            alert,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as err:
        logger.error("ad_alert_send_failed", error=str(err), chat_id=cfg.moderator_chat_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_review.py -v`
Expected: PASS (all seven tests).

- [ ] **Step 6: Commit**

```bash
git add app/presentation/telegram/utils/callback_data.py app/sponsored_ads/review.py tests/unit/test_sponsored_ads_review.py
git commit -m "feat: add moderator ad-review alerts"
```

---

## Task 10: Decision orchestration (`apply_ad_decision`)

**Files:**
- Create: `app/sponsored_ads/decisions.py`
- Test: `tests/unit/test_sponsored_ads_decisions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_sponsored_ads_decisions.py`:

```python
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.sponsored_ads.decisions import apply_ad_decision
from app.sponsored_ads.leads import AdLeadRepository

CHAT_A = -1001
CHAT_B = -1002


class _StubBot:
    """Full bot stub for decision orchestration."""

    def __init__(self, *, dm_ok: bool = True) -> None:
        self._dm_ok = dm_ok
        self.deleted: list[tuple[int, int]] = []
        self.banned: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def me(self) -> SimpleNamespace:
        return SimpleNamespace(username="konnekt_moder_bot")

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        self.deleted.append((chat_id, message_id))
        return True

    async def ban_chat_member(self, chat_id: int, user_id: int) -> bool:
        self.banned.append((chat_id, user_id))
        return True

    async def send_message(self, chat_id: int, text: str, disable_web_page_preview: bool = False) -> SimpleNamespace:
        if chat_id > 0 and not self._dm_ok:
            raise RuntimeError("can't initiate conversation")
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=1)


async def test_delete_decision_cleans_creates_lead_and_reaches(session: AsyncSession) -> None:
    session.add_all([
        Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"),
        Message(chat_id=CHAT_B, user_id=777, message_id=22, message="spam ad"),
    ])
    await session.commit()
    bot = _StubBot(dm_ok=True)

    status = await apply_ad_decision(
        bot, session, action="delete", chat_id=CHAT_A, message_id=11, user_id=777,
    )

    assert set(bot.deleted) == {(CHAT_A, 11), (CHAT_B, 22)}
    assert bot.banned == []
    assert "ЛС" in status
    lead = await AdLeadRepository(session).get_by_id(1)
    assert lead is not None
    assert lead.reached_via == "dm"
    assert lead.snippet == "spam ad"


async def test_delete_decision_falls_back_to_ping(session: AsyncSession) -> None:
    session.add(Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"))
    await session.commit()
    bot = _StubBot(dm_ok=False)

    status = await apply_ad_decision(
        bot, session, action="delete", chat_id=CHAT_A, message_id=11, user_id=777,
    )

    assert "пинг" in status
    lead = await AdLeadRepository(session).get_by_id(1)
    assert lead is not None
    assert lead.reached_via == "ping"


async def test_ban_decision_bans_and_skips_outreach(session: AsyncSession) -> None:
    session.add(Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"))
    await session.commit()
    bot = _StubBot()

    status = await apply_ad_decision(
        bot, session, action="ban", chat_id=CHAT_A, message_id=11, user_id=777,
    )

    assert bot.banned == [(CHAT_A, 777)]
    assert bot.sent == []  # no outreach on ban
    assert "забанен" in status
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_decisions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sponsored_ads.decisions'`.

- [ ] **Step 3: Create `app/sponsored_ads/decisions.py`**

```python
"""Apply a moderator's decision on a flagged ad: delete / ban, then react."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.sponsored_ads import cleanup, outreach
from app.sponsored_ads.leads import AdLeadRepository

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.decisions")

_SNIPPET_CHARS = 300
_REACHED_LABEL = {
    "dm": "написали в ЛС",
    "ping": "пинг в чате",
    "failed": "связаться не удалось",
}


async def apply_ad_decision(
    bot: Bot,
    db: AsyncSession,
    *,
    action: str,
    chat_id: int,
    message_id: int,
    user_id: int,
) -> str:
    """Execute a `delete` or `ban` decision. Returns a short HTML status line.

    `delete` → remove the ad + cross-chat duplicates, create a lead, reach the
    advertiser. `ban` → remove the ad + duplicates, ban the user, no outreach.
    """
    result = await cleanup.delete_ad_duplicates(
        bot,
        db,
        user_id=user_id,
        origin_chat_id=chat_id,
        origin_message_id=message_id,
    )

    if action == "ban":
        try:
            await bot.ban_chat_member(chat_id, user_id)
            banned = True
        except Exception as err:
            logger.warning("ad_ban_failed", error=str(err), user_id=user_id, chat_id=chat_id)
            banned = False
        suffix = "забанен" if banned else "бан не удался"
        return f"🚫 <b>Удалено сообщений: {result.deleted}. Пользователь {suffix}.</b>"

    # action == "delete"
    snippet = result.origin_text[:_SNIPPET_CHARS] if result.origin_text else None
    lead_repo = AdLeadRepository(db)
    lead = await lead_repo.create_lead(chat_id=chat_id, user_id=user_id, snippet=snippet)
    reached_via = await outreach.reach_advertiser(
        bot,
        user_id=user_id,
        origin_chat_id=chat_id,
        lead_id=lead.id,
    )
    await lead_repo.set_reached_via(lead.id, reached_via)
    label = _REACHED_LABEL[reached_via]
    return f"🗑 <b>Удалено сообщений: {result.deleted}. Рекламодатель: {label}.</b>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_sponsored_ads_decisions.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add app/sponsored_ads/decisions.py tests/unit/test_sponsored_ads_decisions.py
git commit -m "feat: add ad decision orchestration"
```

---

## Task 11: Moderator callback handler

**Files:**
- Create: `app/presentation/telegram/handlers/ad_review.py`
- Modify: `app/presentation/telegram/handlers/__init__.py`
- Test: `tests/unit/test_ad_review_handler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ad_review_handler.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.presentation.telegram.handlers.ad_review import process_ad_review
from app.presentation.telegram.utils.callback_data import AdReviewAction

MOD_CHAT = -100999


def _callback(chat_id: int) -> AsyncMock:
    """A CallbackQuery whose `message` lives in chat `chat_id`."""
    message = AsyncMock(spec=types.Message)
    message.chat = SimpleNamespace(id=chat_id)
    message.html_text = "📢 Похоже на рекламу"
    message.text = "📢 Похоже на рекламу"
    callback = AsyncMock()
    callback.message = message
    return callback


async def test_ignores_callback_from_other_chat(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=-1001)  # not the moderator chat
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_reply_markup.assert_not_awaited()
    callback.answer.assert_awaited()


async def test_skip_finalizes_alert(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_reply_markup.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited()


async def test_already_handled_when_claim_fails(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    callback.message.edit_reply_markup.side_effect = RuntimeError("message is not modified")
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_with("Уже обработано")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_ad_review_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.presentation.telegram.handlers.ad_review'`.

- [ ] **Step 3: Create `app/presentation/telegram/handlers/ad_review.py`**

```python
"""Moderator callback handler for flagged-ad alerts."""

from __future__ import annotations

from aiogram import Bot, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads.decisions import apply_ad_decision

logger = get_logger("handlers.ad_review")

ad_review_router = Router()


@ad_review_router.callback_query(AdReviewAction.filter())
async def process_ad_review(
    callback: types.CallbackQuery,
    callback_data: AdReviewAction,
    bot: Bot,
    db: AsyncSession,
) -> None:
    """Handle a moderator tapping skip / delete / ban on an ad alert."""
    message = callback.message
    if not isinstance(message, types.Message) or message.chat.id != settings.sponsored_ads.moderator_chat_id:
        await callback.answer()
        return

    # Claim the alert: removing the keyboard fails if another moderator already acted.
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        await callback.answer("Уже обработано")
        return

    base = message.html_text or message.text or "📢 Похоже на рекламу"

    if callback_data.action == "skip":
        await _finalize(message, base, "⏭ <b>Пропущено.</b>")
        await callback.answer("Пропущено")
        return

    try:
        status = await apply_ad_decision(
            bot,
            db,
            action=callback_data.action,
            chat_id=callback_data.chat_id,
            message_id=callback_data.message_id,
            user_id=callback_data.user_id,
        )
    except Exception as err:
        logger.error("ad_decision_failed", error=str(err), action=callback_data.action)
        await _finalize(message, base, "⚠️ <b>Ошибка при обработке.</b>")
        await callback.answer("Ошибка")
        return

    await _finalize(message, base, status)
    await callback.answer("Готово")


async def _finalize(message: types.Message, base: str, status: str) -> None:
    """Rewrite the alert with the final outcome; best-effort."""
    try:
        await message.edit_text(f"{base}\n\n{status}")
    except Exception as err:
        logger.warning("ad_review_finalize_failed", error=str(err))
```

- [ ] **Step 4: Register the router in `app/presentation/telegram/handlers/__init__.py`**

Change the `from . import ...` line to add `ad_review`:

```python
from . import ad_review, admin, agent_handler, events, groups, moderation, service, start
```

Add this line immediately after `router.include_router(moderation.moderation_router)`:

```python
router.include_router(ad_review.ad_review_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_ad_review_handler.py -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Commit**

```bash
git add app/presentation/telegram/handlers/ad_review.py app/presentation/telegram/handlers/__init__.py tests/unit/test_ad_review_handler.py
git commit -m "feat: add moderator ad-review callback handler"
```

---

## Task 12: `/ads` command, deep links, and `/start` greeting line

**Files:**
- Modify: `app/presentation/telegram/handlers/start.py`
- Test: `tests/unit/test_start_ads.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_start_ads.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdLead
from app.presentation.telegram.handlers.start import ads_command, start_ad_lead, start_ads_info


async def test_ads_command_sends_rate_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "https://telegra.ph/ads")
    message = AsyncMock()
    await ads_command(message)
    message.answer.assert_awaited_once()
    assert "https://telegra.ph/ads" in message.answer.await_args.args[0]


async def test_start_ads_info_sends_rate_card() -> None:
    message = AsyncMock()
    await start_ads_info(message)
    message.answer.assert_awaited_once()


async def test_start_ad_lead_marks_click_and_sends_rate_card(session: AsyncSession) -> None:
    lead = AdLead(chat_id=-1001, user_id=777, snippet="ad")
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session)

    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_start_ads.py -v`
Expected: FAIL with `ImportError: cannot import name 'ads_command' from 'app.presentation.telegram.handlers.start'`.

- [ ] **Step 3: Add imports to `app/presentation/telegram/handlers/start.py`**

Change the aiogram filters import line from:

```python
from aiogram.filters import Command
```

to:

```python
from aiogram import F
from aiogram.filters import Command, CommandObject, CommandStart
```

Add these imports alongside the existing `from app.` imports:

```python
from app.sponsored_ads.leads import AdLeadRepository
from app.sponsored_ads.rate_card import render_rate_card
```

- [ ] **Step 4: Add the three handlers above `start_private`**

Insert these handlers immediately after `router = Router()` and before the `start_private` handler. They are registered before `start_private` so the deep-link handlers win for their payloads; an unrecognized payload falls through to `start_private`.

```python
@router.message(CommandStart(deep_link=True, magic=F.args.regexp(r"^adlead_\d+$")))
async def start_ad_lead(message: types.Message, command: CommandObject, db: AsyncSession) -> None:
    """Smart-link entry t.me/<bot>?start=adlead_<id> — mark the lead clicked, show the rate card."""
    if command.args:
        lead_id = int(command.args.removeprefix("adlead_"))
        await AdLeadRepository(db).mark_clicked(lead_id)
    await message.answer(render_rate_card(), disable_web_page_preview=True)


@router.message(CommandStart(deep_link=True, magic=F.args == "ads"))
async def start_ads_info(message: types.Message) -> None:
    """Deep link t.me/<bot>?start=ads — public advertising info."""
    await message.answer(render_rate_card(), disable_web_page_preview=True)


@router.message(Command("ads", prefix="/!"))
async def ads_command(message: types.Message) -> None:
    """/ads — publicly show advertising info."""
    await message.answer(render_rate_card(), disable_web_page_preview=True)
```

- [ ] **Step 5: Add an advertising line to the `/start` greeting**

In `start_private`, inside the user-facing `text` block, add an `/ads` line. Change:

```python
        "• /report - пожаловаться (нужно переслать сообщение)\n"
    )
```

to:

```python
        "• /report - пожаловаться (нужно переслать сообщение)\n"
        "• /ads - реклама в наших чатах\n"
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_start_ads.py -v`
Expected: PASS (all three tests).

- [ ] **Step 7: Commit**

```bash
git add app/presentation/telegram/handlers/start.py tests/unit/test_start_ads.py
git commit -m "feat: add /ads command and rate-card deep links"
```

---

## Task 13: Wire `HistoryMiddleware` to the moderator alert

**Files:**
- Modify: `app/presentation/telegram/middlewares/history.py`
- Test: `tests/unit/test_history_ad_review_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_history_ad_review_wiring.py`:

```python
import datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.moderation import spam_service
from app.presentation.telegram.middlewares import history as history_mw


def _update(text: str) -> types.Update:
    return types.Update(
        update_id=1,
        message=types.Message(
            message_id=11,
            date=datetime.datetime(2026, 5, 21),
            chat=types.Chat(id=-1001, type="supergroup", title="Prague Chat"),
            from_user=types.User(id=777, is_bot=False, first_name="Ad"),
            text=text,
        ),
    )


async def test_middleware_triggers_ad_review_on_signal(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spam_service, "detect_spam", AsyncMock(return_value=False))
    spy = AsyncMock()
    monkeypatch.setattr(history_mw.ad_review, "notify_moderators", spy)

    middleware = history_mw.HistoryMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {"db": session, "bot": object()}

    result = await middleware(handler, _update("приходите сюда t.me/spampromo срочно"), data)

    assert result == "ok"
    spy.assert_awaited_once()


async def test_middleware_skips_ad_review_without_signal(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spam_service, "detect_spam", AsyncMock(return_value=False))
    spy = AsyncMock()
    monkeypatch.setattr(history_mw.ad_review, "notify_moderators", spy)

    middleware = history_mw.HistoryMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {"db": session, "bot": object()}

    await middleware(handler, _update("just a normal friendly message"), data)

    spy.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_history_ad_review_wiring.py -v`
Expected: FAIL with `AttributeError: module ... 'history' has no attribute 'ad_review'`.

- [ ] **Step 3: Wire the alert into `app/presentation/telegram/middlewares/history.py`**

Add this import alongside the existing `from app.moderation import ...` line:

```python
from app.sponsored_ads import review as ad_review
```

Replace the existing ad-detector block:

```python
            if isinstance(user, types.User):
                try:
                    await ad_detector_service.record_ad_signals(
                        db,
                        chat_id=message.chat.id,
                        user_id=user.id,
                        message_id=message.message_id,
                        text=message.text or message.caption,
                    )
                except Exception as err:
                    logger.error("ad_detector_failed", error=str(err))
```

with:

```python
            if isinstance(user, types.User):
                try:
                    signals = await ad_detector_service.record_ad_signals(
                        db,
                        chat_id=message.chat.id,
                        user_id=user.id,
                        message_id=message.message_id,
                        text=message.text or message.caption,
                    )
                    if signals:
                        await ad_review.notify_moderators(data["bot"], db, message)
                except Exception as err:
                    logger.error("ad_detector_failed", error=str(err))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_history_ad_review_wiring.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full test suite**

Run: `uv run -m pytest tests/unit tests/e2e -x -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/presentation/telegram/middlewares/history.py tests/unit/test_history_ad_review_wiring.py
git commit -m "feat: trigger ad-review alert from history middleware"
```

---

## Task 14: Rewrite the product and domain docs

**Files:**
- Modify: `docs/product/sponsored-ads.md`
- Modify: `docs/domain/sponsored-ads.md`

- [ ] **Step 1: Replace `docs/product/sponsored-ads.md`**

Overwrite the entire file with:

```markdown
# Sponsored Ads (v0 — Rate Card Funnel)

The bot does not sell or broker advertising. It detects ad-spam, lets a
moderator remove it, and points the would-be advertiser at a legitimate paid
path described in an external article.

## Flow

1. The ad-detector flags a message in a managed chat.
2. The bot copies it into the private moderator chat with three buttons:
   **Пропустить**, **Удалить**, **Бан**. The group sees nothing yet.
3. **Пропустить** — false positive, nothing happens.
4. **Удалить** — the message and every identical copy from the same user
   across all managed chats in the last 24h are deleted; the advertiser is
   contacted (DM if possible, otherwise a public ping) with a smart link.
5. **Бан** — same removal, plus the user is banned from the source chat; no
   outreach.
6. The smart link and the `/ads` command open advertising info: a short blurb
   plus a link to the pricing article.

## What it is not

No conversational submission, no price negotiation, no payment handling, no
in-bot pricing. Pricing lives in an externally-maintained article. Selling is
a human job; the bot only redirects.

## Configuration

`SPONSORED_ADS_ENABLED`, `SPONSORED_ADS_MODERATOR_CHAT_ID`,
`SPONSORED_ADS_PRICING_ARTICLE_URL`, `SPONSORED_ADS_SALES_CONTACT`.
```

- [ ] **Step 2: Replace `docs/domain/sponsored-ads.md`**

Overwrite the entire file with:

```markdown
# Sponsored Ads — Domain Rules (v0)

## Entities

- **`ad_leads`** — one row per advertiser redirected to the rate card.
  Fields: `chat_id`, `user_id`, `snippet`, `reached_via` (`dm` / `ping` /
  `failed`), `created_at`, `link_clicked_at`.

## Rules

- An ad alert is sent to moderators only when `SPONSORED_ADS_ENABLED` is true
  and `SPONSORED_ADS_MODERATOR_CHAT_ID` is set.
- Alert dedup: no alert is sent if the same user already posted an identical
  message (normalized: trimmed, whitespace-collapsed, casefolded) within the
  last 24h.
- A moderator decision is authoritative. Any non-skip action deletes the
  message.
- Cleanup deletes every identical message from the same user across all chats
  within the last 24h. Telegram forbids bots deleting messages older than 48h;
  such failures are logged and skipped.
- The advertiser is reached by DM when possible, otherwise by a public ping in
  the source chat. `reached_via` records which.
- The smart link (`?start=adlead_<id>`) marks `link_clicked_at` once; repeat
  clicks do not overwrite it.
- `/ads` and `?start=ads` show the same rate card without lead tracking.
```

- [ ] **Step 3: Commit**

```bash
git add docs/product/sponsored-ads.md docs/domain/sponsored-ads.md
git commit -m "docs: rewrite sponsored ads docs for v0 rate card"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- §3 removal → Task 1. §7 config → Task 2. §6 `ad_leads` → Task 3.
- §5 `text` → Task 4, `leads` → Task 5, `rate_card` → Task 6, `cleanup` → Task 7,
  `outreach` → Task 8, `review` → Task 9, decisions/`ad_review.py` → Tasks 10-11.
- §4 flow: detection→alert wiring → Task 13; smart link / `/ads` → Task 12.
- §8 error handling → covered in Tasks 7-11 (broad catches, idempotent claim).
- §9 testing → unit tests in every task; `apply_ad_decision` (Task 10) and the
  middleware wiring test (Task 13) cover the integration seams. §10 migration → Task 3.
- Docs rewrite (§3) → Task 14.

**2. Placeholders** — none; every step has full code and exact commands.

**3. Type consistency** — `delete_ad_duplicates` returns `CleanupResult(deleted, origin_text)`,
consumed as such in `apply_ad_decision`. `reach_advertiser` returns `"dm"|"ping"|"failed"`,
keyed by `_REACHED_LABEL`. `AdReviewAction(action, chat_id, message_id, user_id)` is built
in `review.build_alert_keyboard` and consumed in `process_ad_review` with matching fields.
`AdLeadRepository` method names (`create_lead`, `set_reached_via`, `mark_clicked`,
`get_by_id`) are consistent across Tasks 5, 10, 12.

**Note on e2e:** the codebase tests Telegram handlers via direct function calls plus stub
bots / `FakeTelegramServer`, not via a live dispatcher. This plan follows that pattern;
`apply_ad_decision` and the middleware wiring test exercise the full logic seam without a
dispatcher. A manual smoke test against a real bot is recommended before enabling
`SPONSORED_ADS_ENABLED` in production.
```
