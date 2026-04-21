# Web UI Phase 2 — Chats + Telethon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/chats`, `/chats/:id`, and three home-dashboard skeletons (Post views, Chat heatmap, Members delta) into live pages backed by chat-activity data from the DB and enrichment from Telethon.

**Architecture:** Add a thin cached Telethon service (`app/webapi/services/telethon_stats.py`) behind a FastAPI `get_telethon()` dep. Chat activity heatmap is built from the existing `messages` table (already populated by moderator handlers — no extra Telethon calls needed). Member-count deltas require history, so we add a new `chat_member_snapshots` table plus a lightweight asyncio snapshot loop on FastAPI startup. Post views come from a new `TelethonClient.get_post_views()` method.

**Tech Stack:** FastAPI + SQLAlchemy async, Telethon (existing client), `cachetools.TTLCache`, SvelteKit 2 + Svelte 5 runes, shadcn-svelte, Tailwind v4.

---

## Scope summary

**New backend:**
- `ChatMemberSnapshot` ORM model + Alembic migration
- `TelethonClient.get_post_views()` method
- `app/webapi/deps.get_telethon()` dependency
- `app/webapi/services/telethon_stats.py` — cached aggregator
- `app/webapi/routes/chats.py` — list + detail
- Extensions to `HomeStats` (post_views, chat_heatmap, members_delta buckets)
- Background snapshot loop wired into `create_app` lifespan

**New frontend:**
- `webui/src/lib/components/chat/HeatmapGrid.svelte`
- Real `webui/src/routes/chats/+page.svelte`
- Real `webui/src/routes/chats/[id]/+page.svelte`
- Upgrade three `SkeletonTile` instances on `/` to live tiles

**Out of scope (Phase 3+):**
- Spam/ad detector + pings feed
- Chat graph / `parent_chat_id`
- Any chat mutations (ban, blacklist, rename) — stays read-only
- `/agent` SSE chat

---

## File Structure

**Created files**
- `alembic/versions/<rev>_add_chat_member_snapshots.py`
- `app/webapi/services/__init__.py`
- `app/webapi/services/telethon_stats.py`
- `app/webapi/routes/chats.py`
- `tests/webapi/test_chats.py`
- `tests/webapi/test_telethon_stats.py`
- `tests/unit/test_chat_member_snapshot_model.py`
- `webui/src/lib/components/chat/HeatmapGrid.svelte`

**Modified files**
- `app/db/models.py` — append `ChatMemberSnapshot`
- `app/telethon/telethon_client.py` — append `get_post_views`
- `app/webapi/deps.py` — add `get_telethon`
- `app/webapi/schemas.py` — new schemas + extend `HomeStats`
- `app/webapi/routes/stats.py` — populate new buckets
- `app/webapi/main.py` — register `chats` router + lifespan snapshot loop
- `webui/src/routes/+page.svelte` — swap 3 skeleton tiles for live
- `webui/src/routes/chats/+page.svelte` — replace `ComingSoon`
- `webui/src/routes/chats/[id]/+page.svelte` — replace `ComingSoon`
- `webui/src/lib/api/types.ts` — regenerated

---

### Task 1: `ChatMemberSnapshot` ORM model + migration

**Files:**
- Modify: `app/db/models.py` (append after existing models, around line 600+)
- Create: `alembic/versions/<rev>_add_chat_member_snapshots.py`
- Create: `tests/unit/test_chat_member_snapshot_model.py`

- [ ] **Step 1: Write model test first**

Create `tests/unit/test_chat_member_snapshot_model.py`:

```python
"""Unit test: ChatMemberSnapshot ORM round-trip."""

from __future__ import annotations

import datetime

import pytest
from app.db.models import ChatMemberSnapshot
from sqlalchemy import select


pytestmark = pytest.mark.asyncio


async def test_chat_member_snapshot_persists_and_queries(session) -> None:
    captured = datetime.datetime(2026, 4, 21, 12, 0, 0)
    snap = ChatMemberSnapshot(
        chat_id=-1001234567890,
        member_count=500,
        captured_at=captured,
    )
    session.add(snap)
    await session.commit()

    rows = (
        await session.execute(
            select(ChatMemberSnapshot).where(ChatMemberSnapshot.chat_id == -1001234567890)
        )
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].member_count == 500
    assert rows[0].captured_at == captured
```

- [ ] **Step 2: Run test → red**

Run: `uv run -m pytest tests/unit/test_chat_member_snapshot_model.py -x`
Expected: `ImportError: cannot import name 'ChatMemberSnapshot'`.

- [ ] **Step 3: Add the model**

Append to `app/db/models.py` (after `AgentEscalation`):

```python
class ChatMemberSnapshot(Base):
    """Periodic member-count observations for managed chats.

    Populated by the webapi's lifespan snapshot loop. Deltas on the home
    dashboard are computed by comparing the most recent snapshot against
    an older baseline (typically 24h / 7d back).
    """

    __tablename__ = "chat_member_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    member_count: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utc_now, index=True)

    def __init__(self, chat_id: int, member_count: int, captured_at: datetime.datetime | None = None) -> None:
        self.chat_id = chat_id
        self.member_count = member_count
        if captured_at is not None:
            self.captured_at = captured_at
```

- [ ] **Step 4: Write migration manually**

Tests use an in-memory SQLite engine with `Base.metadata.create_all`, so they don't need alembic. But production migrations do — create the file explicitly. Find the current head revision:

Run: `ls alembic/versions/ | sort` — pick the newest revision's ID (e.g. `d5e6f7a8b9c0`).

Create `alembic/versions/f6a7b8c9d0e1_add_chat_member_snapshots.py` (use any fresh hex id, set `down_revision` to the head you just found):

```python
"""Add chat_member_snapshots table.

Revision ID: f6a7b8c9d0e1
Revises: <PASTE_HEAD_HERE>
Create Date: 2026-04-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "<PASTE_HEAD_HERE>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_member_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("member_count", sa.Integer, nullable=False),
        sa.Column("captured_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_chat_member_snapshots_chat_id",
        "chat_member_snapshots",
        ["chat_id"],
    )
    op.create_index(
        "ix_chat_member_snapshots_captured_at",
        "chat_member_snapshots",
        ["captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_member_snapshots_captured_at", table_name="chat_member_snapshots")
    op.drop_index("ix_chat_member_snapshots_chat_id", table_name="chat_member_snapshots")
    op.drop_table("chat_member_snapshots")
```

- [ ] **Step 5: Re-run test (SQLite via create_all; no alembic needed)**

Run: `uv run -m pytest tests/unit/test_chat_member_snapshot_model.py -x`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add app/db/models.py alembic/versions/ tests/unit/test_chat_member_snapshot_model.py
git commit -m "feat(db): chat_member_snapshots table for delta computation"
```

---

### Task 2: `TelethonClient.get_post_views`

**Files:**
- Modify: `app/telethon/telethon_client.py` (append method near other getters around line 366)
- Create: `tests/unit/test_telethon_get_post_views.py`

Telegram exposes the `.views` attribute on channel `Message` objects. We fetch them by message IDs via `client.get_messages(channel, ids=[...])`. The method must degrade to `{}` when Telethon is disabled / unavailable.

- [ ] **Step 1: Write test**

Create `tests/unit/test_telethon_get_post_views.py`:

```python
"""Unit test: TelethonClient.get_post_views degrades gracefully and maps views."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import TelethonSettings
from app.telethon.telethon_client import TelethonClient


pytestmark = pytest.mark.asyncio


async def test_returns_empty_when_disabled() -> None:
    settings = TelethonSettings(enabled=False, api_id=1, api_hash="x", session_name="s", phone=None)
    client = TelethonClient(settings=settings)

    result = await client.get_post_views(-100, [1, 2, 3])

    assert result == {}


async def test_returns_view_map_when_connected() -> None:
    settings = TelethonSettings(enabled=True, api_id=1, api_hash="x", session_name="s", phone=None)
    client = TelethonClient(settings=settings)
    client._connected = True  # pretend connected
    fake_client = MagicMock()
    fake_client.get_messages = AsyncMock(return_value=[
        MagicMock(id=1, views=100),
        MagicMock(id=2, views=250),
        None,  # Telegram returns None for missing IDs
    ])
    client._client = fake_client

    result = await client.get_post_views(-100, [1, 2, 3])

    assert result == {1: 100, 2: 250}
```

- [ ] **Step 2: Run test → red**

Run: `uv run -m pytest tests/unit/test_telethon_get_post_views.py -x`
Expected: `AttributeError: ... has no attribute 'get_post_views'`.

- [ ] **Step 3: Add the method**

Append to `app/telethon/telethon_client.py` (before the module-level helper functions at the bottom):

```python
    async def get_post_views(
        self,
        chat_id: int,
        message_ids: list[int],
    ) -> dict[int, int]:
        """Return a {message_id: view_count} map for the given messages.

        Missing or deleted messages are omitted. Returns an empty dict when
        Telethon is disabled or not connected, so callers can treat
        unavailability as "zero data" rather than an error.
        """
        if not self.is_available or self._client is None or not message_ids:
            return {}

        async def _fetch() -> list[Any]:
            assert self._client is not None  # noqa: S101
            result = await self._client.get_messages(chat_id, ids=list(message_ids))
            return result if isinstance(result, list) else [result]

        messages: list[Any] = await self._execute_with_flood_wait(_fetch)
        views: dict[int, int] = {}
        for msg in messages:
            if msg is None:
                continue
            count = getattr(msg, "views", None)
            if count is not None:
                views[msg.id] = int(count)
        return views
```

- [ ] **Step 4: Run test → green**

Run: `uv run -m pytest tests/unit/test_telethon_get_post_views.py -x`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/telethon/telethon_client.py tests/unit/test_telethon_get_post_views.py
git commit -m "feat(telethon): get_post_views returns views by message id"
```

---

### Task 3: `get_telethon()` FastAPI dependency

**Files:**
- Modify: `app/webapi/deps.py`
- Create: `tests/webapi/test_deps_telethon.py` (new; a sibling to existing `test_deps.py`)

`container.get_telethon_client()` is a module-level singleton populated at bot startup. For webapi-only test runs (where the bot didn't start), it's `None`. The dep must surface that as `None` so services can degrade.

- [ ] **Step 1: Write test**

Create `tests/webapi/test_deps_telethon.py`:

```python
"""Test: get_telethon dependency returns container's telethon_client or None."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.webapi.deps import get_telethon


@pytest.mark.asyncio
async def test_returns_none_when_container_empty(monkeypatch) -> None:
    from app.core import container

    monkeypatch.setattr(container, "_telethon_client", None, raising=False)
    result = await get_telethon()
    assert result is None


@pytest.mark.asyncio
async def test_returns_container_client(monkeypatch) -> None:
    from app.core import container

    fake = MagicMock(name="telethon_client")
    monkeypatch.setattr(container, "get_telethon_client", lambda: fake)
    result = await get_telethon()
    assert result is fake
```

- [ ] **Step 2: Run test → red**

Run: `uv run -m pytest tests/webapi/test_deps_telethon.py -x`
Expected: `ImportError: cannot import name 'get_telethon'`.

- [ ] **Step 3: Add the dep**

Extend the existing `if TYPE_CHECKING:` block in `app/webapi/deps.py`:

```python
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.telethon.telethon_client import TelethonClient
```

Then append at the bottom of the file (`from __future__ import annotations` is already in place so the forward ref is resolved lazily):

```python
async def get_telethon() -> TelethonClient | None:
    """Return the process-wide TelethonClient if the main bot has wired one.

    Returns None when running webapi without the bot (tests, standalone
    dev), so callers must handle the no-telethon case gracefully.
    """
    from app.core import container

    return container.get_telethon_client()
```

- [ ] **Step 4: Run test → green**

Run: `uv run -m pytest tests/webapi/test_deps_telethon.py -x`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/webapi/deps.py tests/webapi/test_deps_telethon.py
git commit -m "feat(webapi): get_telethon FastAPI dep"
```

---

### Task 4: `telethon_stats` cached service

**Files:**
- Create: `app/webapi/services/__init__.py`
- Create: `app/webapi/services/telethon_stats.py`
- Create: `tests/webapi/test_telethon_stats.py`

One class, `TelethonStatsService`, wrapping a `TelethonClient | None` plus three `TTLCache` instances — one per method. Per-method TTLs match the spec:
- `get_member_count`: 300s
- `get_post_views_batch`: 600s

Heatmap data comes from the DB, not Telethon, so no cache entry for it here — that logic lives in the chats route.

- [ ] **Step 1: Write tests**

Create `tests/webapi/test_telethon_stats.py`:

```python
"""Test: TelethonStatsService caches results and degrades when telethon is absent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.webapi.services.telethon_stats import TelethonStatsService


pytestmark = pytest.mark.asyncio


async def test_member_count_returns_none_without_telethon() -> None:
    svc = TelethonStatsService(telethon=None)
    assert await svc.get_member_count(-100) is None


async def test_member_count_degrades_when_telethon_unavailable() -> None:
    tc = MagicMock()
    tc.is_available = False
    svc = TelethonStatsService(telethon=tc)
    assert await svc.get_member_count(-100) is None


async def test_member_count_calls_get_chat_info_once_and_caches() -> None:
    tc = MagicMock()
    tc.is_available = True
    chat_info = MagicMock(member_count=420)
    tc.get_chat_info = AsyncMock(return_value=chat_info)
    svc = TelethonStatsService(telethon=tc)

    first = await svc.get_member_count(-100)
    second = await svc.get_member_count(-100)

    assert first == 420
    assert second == 420
    tc.get_chat_info.assert_awaited_once_with(-100)


async def test_post_views_returns_empty_dict_without_telethon() -> None:
    svc = TelethonStatsService(telethon=None)
    assert await svc.get_post_views_batch(-100, [1, 2]) == {}


async def test_post_views_caches_per_chat_id_tuple() -> None:
    tc = MagicMock()
    tc.is_available = True
    tc.get_post_views = AsyncMock(return_value={1: 50})
    svc = TelethonStatsService(telethon=tc)

    first = await svc.get_post_views_batch(-100, [1])
    second = await svc.get_post_views_batch(-100, [1])

    assert first == {1: 50}
    assert second == {1: 50}
    tc.get_post_views.assert_awaited_once()
```

- [ ] **Step 2: Run tests → red (expected missing module)**

Run: `uv run -m pytest tests/webapi/test_telethon_stats.py -x`
Expected: `ModuleNotFoundError: No module named 'app.webapi.services.telethon_stats'`.

- [ ] **Step 3: Create service**

Create `app/webapi/services/__init__.py` (empty).

Create `app/webapi/services/telethon_stats.py`:

```python
"""Cached wrapper around TelethonClient for webapi endpoints.

Spec: docs/superpowers/specs/2026-04-21-web-ui-scope-design.md — Tech layer.

Degrades gracefully when telethon is None or not connected: member count
becomes None, post-views becomes an empty dict. Callers treat missing data
as "zero", so the UI still renders without errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cachetools import TTLCache

if TYPE_CHECKING:
    from app.telethon.telethon_client import TelethonClient

_MEMBER_COUNT_TTL_SECONDS = 300
_POST_VIEWS_TTL_SECONDS = 600
_CACHE_MAXSIZE = 1024


class TelethonStatsService:
    """Per-request-or-longer-lived cache over a few Telethon reads.

    Lifetime: attached to the FastAPI app (one instance per process), so
    caches persist across requests. That's the whole point — it protects
    the Telethon account from flood-wait when multiple tabs refresh.
    """

    def __init__(self, telethon: TelethonClient | None) -> None:
        self._telethon = telethon
        self._member_cache: TTLCache[int, int | None] = TTLCache(
            maxsize=_CACHE_MAXSIZE, ttl=_MEMBER_COUNT_TTL_SECONDS
        )
        self._views_cache: TTLCache[tuple[int, tuple[int, ...]], dict[int, int]] = TTLCache(
            maxsize=_CACHE_MAXSIZE, ttl=_POST_VIEWS_TTL_SECONDS
        )

    async def get_member_count(self, chat_id: int) -> int | None:
        if self._telethon is None or not self._telethon.is_available:
            return None
        if chat_id in self._member_cache:
            return self._member_cache[chat_id]
        info = await self._telethon.get_chat_info(chat_id)
        count = info.member_count if info is not None else None
        self._member_cache[chat_id] = count
        return count

    async def get_post_views_batch(
        self, chat_id: int, message_ids: list[int]
    ) -> dict[int, int]:
        if self._telethon is None or not self._telethon.is_available or not message_ids:
            return {}
        key = (chat_id, tuple(sorted(message_ids)))
        if key in self._views_cache:
            return self._views_cache[key]
        views = await self._telethon.get_post_views(chat_id, list(message_ids))
        self._views_cache[key] = views
        return views
```

- [ ] **Step 4: Run tests → green**

Run: `uv run -m pytest tests/webapi/test_telethon_stats.py -x`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/webapi/services/ tests/webapi/test_telethon_stats.py
git commit -m "feat(webapi): TelethonStatsService with TTL caches"
```

---

### Task 5: Pydantic schemas for chats + home extensions

**Files:**
- Modify: `app/webapi/schemas.py`

Add in order. Keep them minimal — no behaviour.

- [ ] **Step 1: Add chat schemas**

Append to `app/webapi/schemas.py` (after `ChannelDetail`):

```python
class ChatRead(BaseModel):
    """List-page view of a managed chat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    is_forum: bool
    is_welcome_enabled: bool
    is_captcha_enabled: bool
    member_count: int | None = None  # enriched from Telethon, None when unavailable
    created_at: datetime.datetime


class HeatmapCell(BaseModel):
    """One cell of the weekday×hour chat activity grid.

    weekday: 0 = Monday, 6 = Sunday (matches datetime.weekday()).
    hour: 0..23, UTC.
    count: number of messages recorded in `messages` table for that cell
           over the lookback window.
    """

    weekday: int
    hour: int
    count: int


class MemberSnapshotPoint(BaseModel):
    captured_at: datetime.datetime
    member_count: int


class ChatDetail(ChatRead):
    """Full chat payload — adds heatmap grid + member-snapshot series."""

    welcome_message: str | None
    time_delete: int
    modified_at: datetime.datetime
    heatmap: list[HeatmapCell]
    member_snapshots: list[MemberSnapshotPoint]
```

- [ ] **Step 2: Add home-tile schemas + extend `HomeStats`**

Append right after `ChatDetail`:

```python
class PostViewsEntry(BaseModel):
    """Home tile: post view counts for the last N published posts."""

    post_id: int
    channel_id: int
    channel_name: str
    title: str
    published_at: datetime.datetime
    views: int


class ChatHeatmapSummary(BaseModel):
    """Home tile: per-chat total activity over the last 7 days.

    We send totals (not the full grid) to keep the home payload small;
    the full grid lives on /chats/:id.
    """

    chat_id: int
    title: str | None
    total_messages: int


class MembersDeltaEntry(BaseModel):
    """Home tile: members Δ over a window.

    delta_24h / delta_7d: None when no baseline snapshot exists yet
    (first run, or snapshot history too short).
    """

    chat_id: int
    title: str | None
    current: int | None
    delta_24h: int | None
    delta_7d: int | None
```

- [ ] **Step 3: Extend `HomeStats`**

Modify the `HomeStats` class to add three new fields (default `[]` so existing tests still pass):

```python
class HomeStats(BaseModel):
    """Aggregated response backing the home dashboard's live tiles.

    Keeps home to one round-trip; skeleton tiles are FE-only and don't
    appear here.
    """

    drafts: list[DraftBucket]
    scheduled_next_24h: list[ScheduledPostEntry]
    session_cost: SessionCostSummary
    post_views: list[PostViewsEntry] = []
    chat_heatmap: list[ChatHeatmapSummary] = []
    members_delta: list[MembersDeltaEntry] = []
```

- [ ] **Step 4: Import-smoke**

Run: `uv run python -c "from app.webapi.schemas import ChatRead, ChatDetail, HomeStats; HomeStats(drafts=[], scheduled_next_24h=[], session_cost=None).model_dump()"` — this will fail because `session_cost` is required, so instead:

Run: `uv run python -c "from app.webapi.schemas import ChatDetail; print(ChatDetail.model_json_schema()['required'])"`
Expected: a list containing `heatmap`, `member_snapshots`, `welcome_message`, `time_delete`, `modified_at`, plus the ChatRead fields (`id`, `title`, `is_forum`, …, `created_at`).

- [ ] **Step 5: Commit**

```bash
git add app/webapi/schemas.py
git commit -m "feat(webapi): chat + home-tile schemas"
```

---

### Task 6: `GET /api/chats` and `GET /api/chats/{id}` routes

**Files:**
- Create: `app/webapi/routes/chats.py`
- Modify: `app/webapi/main.py` (register router)
- Create: `tests/webapi/test_chats.py`

Heatmap is built from the `messages` table (`chat_id`, `timestamp`). Lookback: 7 days. We bucket by `(weekday, hour)` in Python after loading one `SELECT timestamp FROM messages WHERE chat_id=? AND timestamp >= now-7d`. For large chats this can be hundreds of thousands of rows — fine for dev, but we cap with a `LIMIT 50000` guard anyway.

Member snapshots for detail: the most recent 50 rows from `chat_member_snapshots`, oldest first, so the FE can sparkline-plot them.

- [ ] **Step 1: Write tests**

Create `tests/webapi/test_chats.py`:

```python
"""Tests for /api/chats endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Chat, ChatMemberSnapshot, Message
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session, get_telethon

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    async def _override_get_telethon():
        return None  # no telethon in tests

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_telethon] = _override_get_telethon
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


async def test_list_chats_returns_all(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-1001, title="A"))
        session.add(Chat(id=-1002, title="B"))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/chats")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    titles = sorted(c["title"] for c in body)
    assert titles == ["A", "B"]
    # member_count is None when telethon is absent
    assert all(c["member_count"] is None for c in body)


async def test_chat_detail_heatmap_aggregates_messages(client_factory, db_session_maker) -> None:
    chat_id = -1010
    async with db_session_maker() as session:
        session.add(Chat(id=chat_id, title="C"))
        # 3 messages on Monday 10:00
        monday_10 = datetime.datetime(2026, 4, 20, 10, 30)  # Monday
        for i in range(3):
            msg = Message(chat_id=chat_id, user_id=1, message_id=i)
            msg.timestamp = monday_10
            session.add(msg)
        # 1 message on Tuesday 15:00
        tuesday_15 = datetime.datetime(2026, 4, 21, 15, 0)
        msg = Message(chat_id=chat_id, user_id=1, message_id=99)
        msg.timestamp = tuesday_15
        session.add(msg)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/chats/{chat_id}")

    assert resp.status_code == 200
    body = resp.json()
    cells = {(c["weekday"], c["hour"]): c["count"] for c in body["heatmap"]}
    # Monday (weekday=0), 10:00 → 3
    assert cells.get((0, 10)) == 3
    # Tuesday (weekday=1), 15:00 → 1
    assert cells.get((1, 15)) == 1


async def test_chat_detail_returns_member_snapshots(client_factory, db_session_maker) -> None:
    chat_id = -1020
    base = datetime.datetime(2026, 4, 21, 12, 0)
    async with db_session_maker() as session:
        session.add(Chat(id=chat_id, title="D"))
        for hours_ago, count in [(72, 100), (48, 110), (24, 120), (0, 125)]:
            captured = base - datetime.timedelta(hours=hours_ago)
            session.add(ChatMemberSnapshot(chat_id=chat_id, member_count=count, captured_at=captured))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/chats/{chat_id}")

    body = resp.json()
    counts = [p["member_count"] for p in body["member_snapshots"]]
    assert counts == [100, 110, 120, 125]  # ascending captured_at


async def test_chat_detail_404(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/chats/999999")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests → red**

Run: `uv run -m pytest tests/webapi/test_chats.py -x`
Expected: `ModuleNotFoundError: No module named 'app.webapi.routes.chats'`.

- [ ] **Step 3: Create the route**

Create `app/webapi/routes/chats.py`:

```python
"""Chats — list + detail endpoints.

Heatmap is built from the `messages` table (populated by moderator handlers),
not from Telethon. That's intentional: it's fast, always-fresh for moderated
chats, and doesn't burn Telethon rate limits. Telethon only enriches
member_count. For chats the bot hasn't seen, counts will simply be zero —
we do not paper over that with Telethon history fetches in Phase 2.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot, Message
from app.webapi.deps import get_session, get_telethon, require_super_admin
from app.webapi.schemas import ChatDetail, ChatRead, HeatmapCell, MemberSnapshotPoint
from app.webapi.services.telethon_stats import TelethonStatsService

if TYPE_CHECKING:
    from app.telethon.telethon_client import TelethonClient

router = APIRouter(prefix="/chats", tags=["chats"])

_HEATMAP_LOOKBACK_DAYS = 7
_HEATMAP_MAX_ROWS = 50_000
_SNAPSHOTS_LIMIT = 50


def _build_heatmap(timestamps: list[datetime.datetime]) -> list[HeatmapCell]:
    grid: dict[tuple[int, int], int] = {}
    for ts in timestamps:
        key = (ts.weekday(), ts.hour)
        grid[key] = grid.get(key, 0) + 1
    return [HeatmapCell(weekday=w, hour=h, count=c) for (w, h), c in sorted(grid.items())]


@router.get("", response_model=list[ChatRead])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_session)],
    telethon: Annotated["TelethonClient | None", Depends(get_telethon)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[ChatRead]:
    chats = (await session.execute(select(Chat).order_by(Chat.title))).scalars().all()
    stats = TelethonStatsService(telethon=telethon)
    result: list[ChatRead] = []
    for chat in chats:
        member_count = await stats.get_member_count(chat.id)
        result.append(
            ChatRead(
                id=chat.id,
                title=chat.title,
                is_forum=chat.is_forum,
                is_welcome_enabled=chat.is_welcome_enabled,
                is_captcha_enabled=chat.is_captcha_enabled,
                member_count=member_count,
                created_at=chat.created_at,
            )
        )
    return result


@router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    telethon: Annotated["TelethonClient | None", Depends(get_telethon)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChatDetail:
    chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    since = utc_now() - datetime.timedelta(days=_HEATMAP_LOOKBACK_DAYS)
    timestamps_rows = (
        await session.execute(
            select(Message.timestamp)
            .where(Message.chat_id == chat_id)
            .where(Message.timestamp >= since)
            .limit(_HEATMAP_MAX_ROWS)
        )
    ).all()
    timestamps = [row[0] for row in timestamps_rows]

    snapshot_rows = (
        (
            await session.execute(
                select(ChatMemberSnapshot)
                .where(ChatMemberSnapshot.chat_id == chat_id)
                .order_by(ChatMemberSnapshot.captured_at.desc())
                .limit(_SNAPSHOTS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    snapshots_ascending = list(reversed(snapshot_rows))

    stats = TelethonStatsService(telethon=telethon)
    member_count = await stats.get_member_count(chat.id)

    return ChatDetail(
        id=chat.id,
        title=chat.title,
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        member_count=member_count,
        created_at=chat.created_at,
        welcome_message=chat.welcome_message,
        time_delete=chat.time_delete,
        modified_at=chat.modified_at,
        heatmap=_build_heatmap(timestamps),
        member_snapshots=[
            MemberSnapshotPoint(captured_at=s.captured_at, member_count=s.member_count)
            for s in snapshots_ascending
        ],
    )
```

- [ ] **Step 4: Register router**

Modify `app/webapi/main.py` imports + `include_router` block:

```python
from app.webapi.routes import channels, chats, costs, health, posts, stats
```

```python
    app.include_router(chats.router, prefix="/api")
```

Place the `include_router` call between `channels` and `costs` for alphabetical consistency.

- [ ] **Step 5: Run tests → green**

Run: `uv run -m pytest tests/webapi/test_chats.py -x`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/webapi/routes/chats.py app/webapi/main.py tests/webapi/test_chats.py
git commit -m "feat(webapi): /chats list + detail with heatmap and snapshots"
```

---

### Task 7: Extend `/api/stats/home` with three new buckets

**Files:**
- Modify: `app/webapi/routes/stats.py`
- Modify: `tests/webapi/test_stats.py`

Rules:
- **post_views** — top 5 most recent published posts across channels (last 7 days), enriched via TelethonStats. If telethon is None, we still return the rows with `views=0` so FE can show "no data yet".
- **chat_heatmap** — per-chat total message count over last 7 days, top 8 chats.
- **members_delta** — for each chat with ≥1 snapshot: current = latest snapshot count, delta_24h / delta_7d = current minus the oldest snapshot captured ≥ 24h / 7d ago. `None` if no baseline.

- [ ] **Step 1: Extend existing stats test**

Append to `tests/webapi/test_stats.py`:

```python
async def test_home_includes_post_views(client_factory, db_session_maker) -> None:
    from app.db.models import Channel, ChannelPost
    from app.core.enums import PostStatus
    import datetime

    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-2001, name="V", username="v"))
        post = ChannelPost(channel_id=-2001, external_id="e1", title="P1", post_text="x")
        post.status = PostStatus.APPROVED
        post.telegram_message_id = 42
        post.published_at = datetime.datetime(2026, 4, 21, 10, 0, 0)
        session.add(post)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    assert "post_views" in body
    pvs = body["post_views"]
    assert len(pvs) == 1
    assert pvs[0]["post_id"] > 0
    assert pvs[0]["title"] == "P1"
    assert pvs[0]["views"] == 0  # telethon stubbed to None in tests


async def test_home_includes_chat_heatmap_totals(client_factory, db_session_maker) -> None:
    from app.db.models import Chat, Message
    import datetime

    async with db_session_maker() as session:
        session.add(Chat(id=-3001, title="H"))
        for i in range(5):
            m = Message(chat_id=-3001, user_id=1, message_id=i)
            m.timestamp = datetime.datetime(2026, 4, 21, 12, 0, 0)
            session.add(m)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    assert body["chat_heatmap"][0]["chat_id"] == -3001
    assert body["chat_heatmap"][0]["total_messages"] == 5


async def test_home_members_delta_computes_24h_baseline(client_factory, db_session_maker) -> None:
    from app.db.models import Chat, ChatMemberSnapshot
    import datetime
    from app.core.time import utc_now

    now = utc_now()
    async with db_session_maker() as session:
        session.add(Chat(id=-4001, title="M"))
        session.add(ChatMemberSnapshot(
            chat_id=-4001, member_count=100,
            captured_at=now - datetime.timedelta(hours=25),
        ))
        session.add(ChatMemberSnapshot(
            chat_id=-4001, member_count=110,
            captured_at=now - datetime.timedelta(minutes=5),
        ))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    delta = next(d for d in body["members_delta"] if d["chat_id"] == -4001)
    assert delta["current"] == 110
    assert delta["delta_24h"] == 10
    assert delta["delta_7d"] is None  # no baseline ≥7d old yet
```

Also add the telethon override to the existing `client_factory` fixture if not already present — check the file, and if there's already `get_telethon` override, skip. Otherwise add:

```python
    from app.webapi.deps import get_telethon
    async def _override_get_telethon(): return None
    app.dependency_overrides[get_telethon] = _override_get_telethon
    ...
    app.dependency_overrides.pop(get_telethon, None)
```

- [ ] **Step 2: Run tests → red (new keys missing)**

Run: `uv run -m pytest tests/webapi/test_stats.py -x`
Expected: `KeyError: 'post_views'` (or similar).

- [ ] **Step 3: Extend the route**

Modify `app/webapi/routes/stats.py`:

1. Import additions at top:

```python
from app.core.enums import PostStatus
from app.db.models import Chat, ChannelPost, ChatMemberSnapshot, Message
from app.webapi.deps import get_session, get_telethon, require_super_admin
from app.webapi.schemas import (
    ChatHeatmapSummary,
    DraftBucket,
    HomeStats,
    MembersDeltaEntry,
    PostViewsEntry,
    ScheduledPostEntry,
    SessionCostSummary,
)
from app.webapi.services.telethon_stats import TelethonStatsService

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.telethon.telethon_client import TelethonClient
```

2. Add new module-level constants:

```python
_POST_VIEWS_TOP_N = 5
_POST_VIEWS_LOOKBACK_DAYS = 7
_CHAT_HEATMAP_TOP_N = 8
_CHAT_HEATMAP_LOOKBACK_DAYS = 7
```

3. Extend `home_stats` signature with `telethon` dep:

```python
async def home_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    telethon: Annotated["TelethonClient | None", Depends(get_telethon)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> HomeStats:
```

4. After computing `scheduled`, add:

```python
    # --- Post views (last N published posts, enriched via Telethon) ---
    views_lookback = now - datetime.timedelta(days=_POST_VIEWS_LOOKBACK_DAYS)
    published_rows = (
        await session.execute(
            select(ChannelPost, Channel.name)
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.status == PostStatus.APPROVED)
            .where(ChannelPost.published_at.is_not(None))
            .where(ChannelPost.published_at >= views_lookback)
            .where(ChannelPost.telegram_message_id.is_not(None))
            .order_by(ChannelPost.published_at.desc())
            .limit(_POST_VIEWS_TOP_N)
        )
    ).all()

    stats_svc = TelethonStatsService(telethon=telethon)
    # Group message IDs by channel to batch Telethon calls.
    views_by_channel: dict[int, dict[int, int]] = {}
    channel_to_msgs: dict[int, list[int]] = {}
    for post, _name in published_rows:
        channel_to_msgs.setdefault(post.channel_id, []).append(post.telegram_message_id)
    for ch_id, msg_ids in channel_to_msgs.items():
        views_by_channel[ch_id] = await stats_svc.get_post_views_batch(ch_id, msg_ids)

    post_views = [
        PostViewsEntry(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_name=ch_name or f"#{post.channel_id}",
            title=post.title,
            published_at=post.published_at,
            views=views_by_channel.get(post.channel_id, {}).get(post.telegram_message_id, 0),
        )
        for post, ch_name in published_rows
    ]

    # --- Chat heatmap summary (top N chats by total messages, last 7d) ---
    heatmap_since = now - datetime.timedelta(days=_CHAT_HEATMAP_LOOKBACK_DAYS)
    total_msgs = func.count(Message.id).label("total_msgs")
    heatmap_rows = (
        await session.execute(
            select(Message.chat_id, Chat.title, total_msgs)
            .join(Chat, Chat.id == Message.chat_id, isouter=True)
            .where(Message.timestamp >= heatmap_since)
            .group_by(Message.chat_id, Chat.title)
            .order_by(total_msgs.desc())
            .limit(_CHAT_HEATMAP_TOP_N)
        )
    ).all()
    chat_heatmap = [
        ChatHeatmapSummary(chat_id=row.chat_id, title=row.title, total_messages=int(row.total_msgs))
        for row in heatmap_rows
    ]

    # --- Members delta ---
    members_delta = await _compute_members_delta(session, now)
```

5. Add the helper `_compute_members_delta` at module scope (after `_SCHEDULED_WINDOW_HOURS`):

```python
async def _compute_members_delta(
    session: AsyncSession, now: datetime.datetime
) -> list[MembersDeltaEntry]:
    """For every chat with ≥1 snapshot: current count + Δ over 24h / 7d.

    Baseline = oldest snapshot whose captured_at >= (now - window). If none,
    delta is None. This is cheaper than per-chat queries because we fetch all
    relevant snapshots once and bucket in Python.
    """
    lookback_7d = now - datetime.timedelta(days=7)
    rows = (
        (
            await session.execute(
                select(ChatMemberSnapshot, Chat.title)
                .join(Chat, Chat.id == ChatMemberSnapshot.chat_id, isouter=True)
                .where(ChatMemberSnapshot.captured_at >= lookback_7d)
                .order_by(ChatMemberSnapshot.captured_at.asc())
            )
        ).all()
    )
    by_chat: dict[int, list[tuple[datetime.datetime, int, str | None]]] = {}
    for snap, title in rows:
        by_chat.setdefault(snap.chat_id, []).append((snap.captured_at, snap.member_count, title))

    out: list[MembersDeltaEntry] = []
    for chat_id, points in by_chat.items():
        if not points:
            continue
        title = points[-1][2]
        current = points[-1][1]
        baseline_24h = next(
            (c for ts, c, _ in points if ts <= now - datetime.timedelta(hours=24)),
            None,
        )
        baseline_7d = next(
            (c for ts, c, _ in points if ts <= now - datetime.timedelta(days=7)),
            None,
        )
        out.append(
            MembersDeltaEntry(
                chat_id=chat_id,
                title=title,
                current=current,
                delta_24h=(current - baseline_24h) if baseline_24h is not None else None,
                delta_7d=(current - baseline_7d) if baseline_7d is not None else None,
            )
        )
    return out
```

6. Update the final `return`:

```python
    return HomeStats(
        drafts=drafts,
        scheduled_next_24h=scheduled,
        session_cost=SessionCostSummary.from_tracker(get_session_summary()),
        post_views=post_views,
        chat_heatmap=chat_heatmap,
        members_delta=members_delta,
    )
```

- [ ] **Step 4: Run stats tests → green**

Run: `uv run -m pytest tests/webapi/test_stats.py -x`
Expected: all passing, including the 3 new tests.

- [ ] **Step 5: Commit**

```bash
git add app/webapi/routes/stats.py tests/webapi/test_stats.py
git commit -m "feat(webapi): extend /stats/home with post_views, chat_heatmap, members_delta"
```

---

### Task 8: Background member-snapshot loop on lifespan

**Files:**
- Modify: `app/webapi/main.py`
- Create: `app/webapi/snapshot_loop.py`
- Create: `tests/webapi/test_snapshot_loop.py`

One task per process. On startup, spawn an asyncio task that every `SNAPSHOT_INTERVAL_SECONDS` loops over `Chat` rows, calls Telethon `get_chat_info`, writes a `ChatMemberSnapshot` row. Skips when telethon is None or unavailable. Cancelled cleanly on shutdown.

- [ ] **Step 1: Write test**

Create `tests/webapi/test_snapshot_loop.py`:

```python
"""Test: snapshot_once reads chats, queries telethon, writes snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.db.models import Chat, ChatMemberSnapshot
from app.webapi.snapshot_loop import snapshot_once
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_snapshot_once_noop_without_telethon(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-1, title="X"))
        await session.commit()

    await snapshot_once(session_maker=db_session_maker, telethon=None)

    async with db_session_maker() as session:
        rows = (await session.execute(select(ChatMemberSnapshot))).scalars().all()
    assert rows == []


async def test_snapshot_once_writes_rows_for_each_chat(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-100, title="A"))
        session.add(Chat(id=-200, title="B"))
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(side_effect=[
        MagicMock(member_count=50),
        MagicMock(member_count=80),
    ])

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        rows = (await session.execute(select(ChatMemberSnapshot).order_by(ChatMemberSnapshot.chat_id))).scalars().all()
    assert [(r.chat_id, r.member_count) for r in rows] == [(-200, 80), (-100, 50)]
```

- [ ] **Step 2: Run test → red**

Run: `uv run -m pytest tests/webapi/test_snapshot_loop.py -x`
Expected: `ModuleNotFoundError: No module named 'app.webapi.snapshot_loop'`.

- [ ] **Step 3: Create the loop**

Create `app/webapi/snapshot_loop.py`:

```python
"""Periodic member-count snapshot collector.

Runs as a single background asyncio task for the lifetime of the webapi
process. Intentionally simple: one query per chat per tick, no concurrency,
no deduplication. If the process dies, we lose the in-flight tick; no
state is corrupted because each snapshot is an independent row.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Chat, ChatMemberSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    from app.telethon.telethon_client import TelethonClient

logger = get_logger("webapi.snapshot_loop")

SNAPSHOT_INTERVAL_SECONDS = 3600  # 1 hour


async def snapshot_once(
    *,
    session_maker: "async_sessionmaker[AsyncSession]",
    telethon: "TelethonClient | None",
) -> int:
    """Capture one snapshot per chat. Returns the number of rows written."""
    if telethon is None or not telethon.is_available:
        logger.info("snapshot_once skipped — telethon unavailable")
        return 0

    written = 0
    async with session_maker() as session:
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            try:
                info = await telethon.get_chat_info(chat.id)
            except Exception as e:  # noqa: BLE001
                logger.warning("get_chat_info failed", chat_id=chat.id, error=str(e))
                continue
            if info is None or info.member_count is None:
                continue
            session.add(ChatMemberSnapshot(chat_id=chat.id, member_count=info.member_count))
            written += 1
        await session.commit()
    logger.info("snapshot_once committed", rows=written)
    return written


async def run_snapshot_loop(
    *,
    session_maker: "async_sessionmaker[AsyncSession]",
    telethon: "TelethonClient | None",
    interval_seconds: int = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Forever-loop. Cancelled on app shutdown via task.cancel()."""
    while True:
        try:
            await snapshot_once(session_maker=session_maker, telethon=telethon)
        except Exception:
            logger.exception("snapshot_loop iteration failed")
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Wire lifespan into `create_app`**

Modify `app/webapi/main.py`:

```python
"""FastAPI app factory."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import get_logger
from app.db.session import create_session_maker
from app.webapi.routes import channels, chats, costs, health, posts, stats
from app.webapi.snapshot_loop import run_snapshot_loop

if TYPE_CHECKING:
    from fastapi import FastAPI as _FastAPI  # noqa: F401


logger = get_logger("webapi.main")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from app.core import container

    session_maker = create_session_maker()
    telethon = container.get_telethon_client()
    task: asyncio.Task | None = None
    if telethon is not None:
        task = asyncio.create_task(
            run_snapshot_loop(session_maker=session_maker, telethon=telethon)
        )
        logger.info("snapshot_loop started")
    else:
        logger.info("snapshot_loop not started — telethon unavailable")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("snapshot_loop stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Moderator Bot Admin API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(posts.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(chats.router, prefix="/api")
    app.include_router(costs.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")

    return app


app = create_app()
```

- [ ] **Step 5: Run test + full webapi suite**

Run: `uv run -m pytest tests/webapi tests/unit -x`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/webapi/snapshot_loop.py app/webapi/main.py tests/webapi/test_snapshot_loop.py
git commit -m "feat(webapi): background chat-member snapshot loop"
```

---

### Task 9: Regenerate OpenAPI TypeScript types

**Files:**
- Modify: `webui/src/lib/api/types.ts` (regenerated)

- [ ] **Step 1: Start backend**

Run: `uv run uvicorn app.webapi.main:app --port 8787 &`
Wait ~1s for it to bind.

- [ ] **Step 2: Regenerate types**

Run: `cd webui && pnpm run api:sync`
Expected: `webui/src/lib/api/types.ts` is regenerated. Verify it now exports `ChatRead`, `ChatDetail`, `HeatmapCell`, `MemberSnapshotPoint`, `PostViewsEntry`, `ChatHeatmapSummary`, `MembersDeltaEntry`.

Run: `grep -E 'ChatRead|HeatmapCell|PostViewsEntry|MembersDeltaEntry' webui/src/lib/api/types.ts | head`
Expected: 4+ matches.

- [ ] **Step 3: Stop backend**

Kill the uvicorn background process (`kill %1` or find its PID with `lsof -i :8787`).

- [ ] **Step 4: Commit**

```bash
git add webui/src/lib/api/types.ts
git commit -m "chore(webui): regenerate OpenAPI types for Phase 2"
```

---

### Task 10: `HeatmapGrid.svelte` component

**Files:**
- Create: `webui/src/lib/components/chat/HeatmapGrid.svelte`

7×24 grid. Days = rows (Mon–Sun), hours = columns. Each cell is a small square whose opacity scales with count relative to the grid max. Render in CSS grid. No tooltips needed in v1 — the tile primitive handles title.

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
	import type { components } from '$lib/api/types';

	type HeatmapCell = components['schemas']['HeatmapCell'];
	type Props = { cells: HeatmapCell[] };
	let { cells }: Props = $props();

	const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

	const countByKey = $derived.by(() => {
		const map = new Map<string, number>();
		for (const c of cells) map.set(`${c.weekday}:${c.hour}`, c.count);
		return map;
	});

	const maxCount = $derived(Math.max(1, ...cells.map((c) => c.count)));

	function cellOpacity(weekday: number, hour: number): number {
		const n = countByKey.get(`${weekday}:${hour}`) ?? 0;
		if (n === 0) return 0;
		// gamma-ish scale so modest activity is visible
		return 0.15 + 0.85 * Math.sqrt(n / maxCount);
	}

	function cellCount(weekday: number, hour: number): number {
		return countByKey.get(`${weekday}:${hour}`) ?? 0;
	}
</script>

<div class="space-y-1">
	<div class="grid grid-cols-[3rem_repeat(24,1fr)] items-center gap-[2px] text-[10px] text-zinc-500">
		<div></div>
		{#each Array(24) as _, h}
			<div class="text-center">{h % 6 === 0 ? h : ''}</div>
		{/each}
	</div>

	{#each weekdayLabels as label, weekday}
		<div class="grid grid-cols-[3rem_repeat(24,1fr)] items-center gap-[2px]">
			<div class="text-[10px] text-zinc-500">{label}</div>
			{#each Array(24) as _, hour}
				<div
					class="aspect-square rounded-sm border border-zinc-200 bg-emerald-500"
					style:opacity={cellOpacity(weekday, hour)}
					title="{label} {hour}:00 — {cellCount(weekday, hour)}"
				></div>
			{/each}
		</div>
	{/each}
</div>
```

- [ ] **Step 2: Visual smoke in dev server**

Dev server is already running (or restart via `cd webui && pnpm run dev --host 0.0.0.0`). The component is not yet mounted anywhere — we'll verify rendering in Task 12.

- [ ] **Step 3: Commit**

```bash
git add webui/src/lib/components/chat/HeatmapGrid.svelte
git commit -m "feat(webui): HeatmapGrid component"
```

---

### Task 11: `/chats` list page

**Files:**
- Modify: `webui/src/routes/chats/+page.svelte`

Table view. Columns: Title, Members, Captcha, Welcome, Created. Member count shown as "—" when null (telethon missing). Row click → `/chats/[id]`.

- [ ] **Step 1: Replace placeholder**

Overwrite `webui/src/routes/chats/+page.svelte`:

```svelte
<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { goto } from '$app/navigation';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);

	function fmtMembers(n: number | null | undefined): string {
		return n === null || n === undefined ? '—' : n.toLocaleString();
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString();
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Chats</h2>
		{#if chats.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {chats.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	<Card.Root>
		<Card.Content class="pt-6">
			{#if chats.loading}
				<p class="text-sm text-zinc-500">Loading…</p>
			{:else if chats.error}
				<p class="text-sm text-red-600">Error: {chats.error}</p>
			{:else if !chats.data || chats.data.length === 0}
				<p class="text-sm text-zinc-500">No chats registered yet.</p>
			{:else}
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Title</Table.Head>
							<Table.Head class="w-24">Members</Table.Head>
							<Table.Head class="w-24">Captcha</Table.Head>
							<Table.Head class="w-24">Welcome</Table.Head>
							<Table.Head class="w-28">Created</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each chats.data as chat (chat.id)}
							<Table.Row
								class="cursor-pointer hover:bg-zinc-50"
								onclick={() => goto(`/chats/${chat.id}`)}
							>
								<Table.Cell class="font-medium">{chat.title ?? `#${chat.id}`}</Table.Cell>
								<Table.Cell>{fmtMembers(chat.member_count)}</Table.Cell>
								<Table.Cell>{chat.is_captcha_enabled ? 'on' : 'off'}</Table.Cell>
								<Table.Cell>{chat.is_welcome_enabled ? 'on' : 'off'}</Table.Cell>
								<Table.Cell class="text-xs text-zinc-500">{fmtDate(chat.created_at)}</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
```

- [ ] **Step 2: Visual smoke**

Open `http://46.225.117.31:5173/chats` in browser. Expect the table loaded with rows matching DB contents. If no chats exist, expect the empty-state message.

- [ ] **Step 3: Commit**

```bash
git add webui/src/routes/chats/+page.svelte
git commit -m "feat(webui): /chats list page"
```

---

### Task 12: `/chats/[id]` detail page

**Files:**
- Modify: `webui/src/routes/chats/[id]/+page.svelte`

Shows: chat metadata (title, members, captcha, welcome), heatmap (using `HeatmapGrid`), member snapshot sparkline (simple svg polyline).

- [ ] **Step 1: Replace placeholder**

Overwrite `webui/src/routes/chats/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';
	import * as Card from '$lib/components/ui/card/index.js';
	import HeatmapGrid from '$lib/components/chat/HeatmapGrid.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type ChatDetail = components['schemas']['ChatDetail'];

	const chatId = $derived(page.params.id);
	const detail = useLivePoll<ChatDetail>(`/api/chats/${chatId}`, 60_000);

	function sparklinePath(points: { member_count: number }[]): string {
		if (points.length === 0) return '';
		const w = 240;
		const h = 48;
		const max = Math.max(...points.map((p) => p.member_count));
		const min = Math.min(...points.map((p) => p.member_count));
		const span = Math.max(1, max - min);
		return points
			.map((p, i) => {
				const x = (i / Math.max(1, points.length - 1)) * w;
				const y = h - ((p.member_count - min) / span) * h;
				return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header>
		<h2 class="text-lg font-semibold tracking-tight">
			{detail.data?.title ?? `Chat #${chatId}`}
		</h2>
		{#if detail.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {detail.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	{#if detail.loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if detail.error}
		<p class="text-sm text-red-600">Error: {detail.error}</p>
	{:else if detail.data}
		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Overview</Card.Title></Card.Header>
			<Card.Content class="grid grid-cols-2 gap-2 text-sm">
				<div>Members: <strong>{detail.data.member_count ?? '—'}</strong></div>
				<div>Forum: {detail.data.is_forum ? 'yes' : 'no'}</div>
				<div>Captcha: {detail.data.is_captcha_enabled ? 'on' : 'off'}</div>
				<div>Welcome: {detail.data.is_welcome_enabled ? 'on' : 'off'}</div>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Activity heatmap (7 days, UTC)</Card.Title></Card.Header>
			<Card.Content>
				<HeatmapGrid cells={detail.data.heatmap} />
				{#if detail.data.heatmap.length === 0}
					<p class="mt-2 text-xs text-zinc-500">No messages recorded for this chat yet.</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Members over time</Card.Title></Card.Header>
			<Card.Content>
				{#if detail.data.member_snapshots.length === 0}
					<p class="text-xs text-zinc-500">No snapshots yet. First snapshot will appear within an hour of bot startup.</p>
				{:else}
					<svg width="240" height="48" class="text-emerald-600">
						<path d={sparklinePath(detail.data.member_snapshots)} fill="none" stroke="currentColor" stroke-width="1.5" />
					</svg>
					<p class="text-xs text-zinc-500">
						{detail.data.member_snapshots.length} snapshots
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
```

- [ ] **Step 2: Visual smoke**

Open `http://46.225.117.31:5173/chats/<SOME-CHAT-ID>` in browser. Heatmap cells should render (sparse is fine).

- [ ] **Step 3: Commit**

```bash
git add webui/src/routes/chats/[id]/+page.svelte
git commit -m "feat(webui): /chats/:id detail with heatmap and member sparkline"
```

---

### Task 13: Upgrade home tiles — Post views, Chat heatmap, Members delta

**Files:**
- Modify: `webui/src/routes/+page.svelte`

Replace the three `<SkeletonTile />` instances for Post views / Chats heatmap / Members delta with live tiles backed by the new `HomeStats` fields. Keep Spam pings + Chat graph as skeletons (Phase 3).

- [ ] **Step 1: Replace the three skeletons**

In `webui/src/routes/+page.svelte`, modify the grid block. Delete the three lines:

```svelte
<SkeletonTile title="Post views" phase={2} hint="Requires Telethon aggregation." />
<SkeletonTile title="Chats heatmap" phase={2} hint="Requires Telethon aggregation." />
<SkeletonTile title="Members delta" phase={2} hint="Requires Telethon aggregation." />
```

Replace with:

```svelte
<ListTile
    title="Post views (recent)"
    items={(stats.data?.post_views ?? []).map((p) => ({
        primary: p.title,
        secondary: p.views === 0 ? 'no data' : p.views.toLocaleString()
    }))}
    empty={stats.loading ? 'loading…' : 'No published posts yet'}
/>
<ListTile
    title="Chats heatmap (7d total)"
    items={(stats.data?.chat_heatmap ?? []).map((c) => ({
        primary: c.title ?? `#${c.chat_id}`,
        secondary: c.total_messages.toLocaleString()
    }))}
    empty={stats.loading ? 'loading…' : 'No activity recorded'}
/>
<ListTile
    title="Members Δ (24h)"
    items={(stats.data?.members_delta ?? []).map((m) => {
        const d = m.delta_24h;
        const sign = d === null || d === undefined ? '' : d > 0 ? '+' : '';
        const secondary =
            d === null || d === undefined
                ? `${m.current ?? '—'} (no baseline)`
                : `${m.current?.toLocaleString() ?? '—'} (${sign}${d})`;
        return { primary: m.title ?? `#${m.chat_id}`, secondary };
    })}
    empty={stats.loading ? 'loading…' : 'No snapshots yet'}
/>
```

- [ ] **Step 2: Visual smoke**

Open `http://46.225.117.31:5173/` in browser. Expect:
- "Drafts queue", "Scheduled next 24h", "LLM cost (session)" — still live from Phase 1.
- Three former skeletons now showing real data (or tidy empty states if there's no data yet).
- "Spam pings" + "Chat graph" still skeletons (Phase 3 badge).

- [ ] **Step 3: Commit**

```bash
git add webui/src/routes/+page.svelte
git commit -m "feat(webui): home tiles for post views, chat heatmap, members delta"
```

---

### Task 14: End-to-end smoke + final commit

**Files:**
- None (verification only).

- [ ] **Step 1: Full backend test suite**

Run: `uv run -m pytest -x`
Expected: all tests pass (expect ~15 new tests across the phase).

- [ ] **Step 2: Lint + type-check**

Run: `uv run ruff check app tests && uv run ruff format --check app tests && uv run ty check app tests`
Expected: all clean.

- [ ] **Step 3: Svelte check**

Run: `cd webui && pnpm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Manual route tour**

Open each of the following in a browser and confirm the expected state:
- `/` — 8 tiles, 6 live (drafts, scheduled, cost, post views, chats heatmap, members Δ), 2 skeleton (spam pings, chat graph).
- `/chats` — table of chats, clickable rows.
- `/chats/<id>` — overview + heatmap + member sparkline.
- `/posts`, `/posts/<id>`, `/channels`, `/channels/<id>`, `/costs` — still work from Phase 1.

Record screenshots or a short GIF for the PR description.

- [ ] **Step 5: Push branch**

```bash
git push -u origin feat/web-ui-phase-2-chats-telethon
```

- [ ] **Step 6: Open PR**

```bash
gh pr create --title "feat(webui): Phase 2 — chats + telethon enrichment" --body "$(cat <<'EOF'
## Summary
- `/chats` + `/chats/:id` now render real data (member count, 7-day heatmap, member-count history)
- Home dashboard upgraded: post views, chat heatmap totals, members Δ tiles are live
- Telethon access wrapped in cached service + background snapshot loop for delta computation

Implements Phase 2 of `docs/superpowers/specs/2026-04-21-web-ui-scope-design.md`.

## Test plan
- [ ] Full backend pytest suite passes
- [ ] `svelte-check` clean
- [ ] Route tour: `/`, `/chats`, `/chats/:id` render expected data
- [ ] Telethon-disabled mode still renders (member_count = —, views = 0)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Notes for the implementer

- **DB vs Telethon boundary:** Heatmap is DB-only (from `messages` table); post views and member counts are Telethon. This is intentional — keeps the UI responsive and doesn't burn Telethon quotas on every page load.
- **Graceful degradation:** every Telethon consumer must handle `None`. Tests override `get_telethon` with `return None`. Never 500 because telethon is down.
- **Cache lifetimes:** `TelethonStatsService` is instantiated per-request right now (inside route handlers). That's fine for Phase 2 — caches help within a single request's fan-out (e.g. `/stats/home` calls `get_post_views_batch` once per channel). If you need cross-request caching later, move the service onto `app.state` in `create_app`.
- **Snapshots require the main bot to be up** (telethon is wired in the bot process). During a stand-alone webapi run, the loop logs "telethon unavailable" and exits — members delta stays empty. That's acceptable for dev.
- **Timezone:** `messages.timestamp` is UTC-naive; heatmap `weekday` / `hour` are UTC. The FE already says "(UTC)" on the heatmap card. Don't convert.
