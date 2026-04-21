# Web UI Phase 1 (Home + DB Pages) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 0 shell into a working read-only dashboard — home with 8 tiles (3 live, 5 skeleton), a filterable Posts list + detail, Channels list + detail, and a Costs view. No mutations. All data comes from the existing DB or the in-process `cost_tracker` module.

**Architecture:** Seven new FastAPI endpoints grouped into four routers (posts detail, channels, costs, stats). Seven new Svelte pages wired through the existing `apiFetch` + generated OpenAPI types. The Home page owns tile composition; a single `useLivePoll` hook drives refresh across dashboards (polling, 30s default). Costs surface the in-memory session summary with an explicit "since last bot restart" caveat — persistent cost storage is deferred to Phase 1.5.

**Tech Stack:** Same as Phase 0 (SvelteKit 2 + Svelte 5 runes, TypeScript, Tailwind v4, shadcn-svelte, FastAPI + SQLAlchemy async, pytest). Additions: the `$lib/hooks/useLivePoll.ts` hook (pure Svelte 5, no deps).

**Branch:** `feat/web-ui-phase-1-home-pages` — branch from current `main` (after Phase 0 merge).

**Design doc:** `docs/superpowers/specs/2026-04-21-web-ui-scope-design.md` (Phase 1 section).

---

## Key data-layer facts (for implementers)

- `ChannelPost` (table `channel_posts`): `id, channel_id, external_id, title, post_text, status (PostStatus), image_url, image_urls, source_url, scheduled_at, published_at, created_at, source_items (JSON)`. See `app/db/models.py:400+`.
- `Channel` (table `channels`): `id, telegram_id, username, name, description, language, enabled, review_chat_id, max_posts_per_day, posting_schedule, publish_schedule, discovery_query, footer_template, critic_enabled, created_at, modified_at`. See `app/db/models.py:252+`.
- `ChannelSource` (table `channel_sources`): `id, channel_id, url, source_type, title, language, enabled, relevance_score, error_count, last_fetched_at, last_error, created_at`. Joined on `channel_id` (which stores `Channel.telegram_id`, not `Channel.id` — verify in `app/channel/sources.py` if unsure). See `app/db/models.py:338+`.
- `PostStatus` values (enum at `app/core/enums.py`): `DRAFT`, `SENT_FOR_REVIEW`, `APPROVED`, `REJECTED`, `PUBLISHED`, `SCHEDULED`, `FAILED`, `DELETED`. String StrEnum.
- `cost_tracker` (module at `app/channel/cost_tracker.py`): `get_session_summary() -> dict[str, Any]` returns `{total_cost_usd, total_input_tokens, total_output_tokens, by_model: dict[model_name, {cost, input, output, calls}], total_calls, session_started_at}`. In-memory only (`_usage_history: list[LLMUsage]`).

---

## File structure at end of Phase 1

```
app/webapi/
├── deps.py                         (unchanged)
├── main.py                         + mount channels, costs, stats routers
├── schemas.py                      + PostDetail, ChannelRead, ChannelDetail,
│                                     ChannelSourceRead, HomeStats,
│                                     SessionCostSummary
└── routes/
    ├── health.py                   (unchanged)
    ├── posts.py                    + channel_id filter; + GET /posts/{id}
    ├── channels.py                 NEW  list + detail
    ├── costs.py                    NEW  GET /costs/session
    └── stats.py                    NEW  GET /stats/home

tests/webapi/
├── conftest.py                     (reuse)
├── test_deps.py                    (unchanged)
├── test_posts.py                   NEW  list filter + detail endpoint
├── test_channels.py                NEW  list + detail
├── test_costs.py                   NEW  session summary
└── test_stats.py                   NEW  home aggregator shape

webui/src/lib/
├── api/
│   ├── client.ts                   (unchanged)
│   └── types.ts                    regenerated from expanded OpenAPI
├── hooks/
│   └── useLivePoll.ts              NEW  reusable polling hook
└── components/
    ├── app-shell/                  (unchanged)
    ├── ComingSoon.svelte           (unchanged)
    └── home/
        ├── Tile.svelte             NEW  base tile shell (title, children, actions slot)
        ├── StatTile.svelte         NEW  "42 drafts" number-with-caption variant
        ├── ListTile.svelte         NEW  small list inside a tile
        └── SkeletonTile.svelte     NEW  Phase-labeled empty state

webui/src/routes/
├── +page.svelte                    replace skeleton with home dashboard
├── posts/+page.svelte              replace skeleton with real list + filters
├── posts/[id]/+page.svelte         replace skeleton with post detail
├── channels/+page.svelte           replace skeleton with real list
├── channels/[id]/+page.svelte      replace skeleton with real detail
└── costs/+page.svelte              replace skeleton with session summary
```

---

## Preflight

- [ ] **Confirm state**

```bash
git checkout main && git pull origin main
git log -1 --oneline   # should include "Phase 0 foundation (#71)"
uv run -m pytest tests/webapi -v   # 2 passed
pnpm --dir webui run check         # 0 errors
```

- [ ] **Create the branch**

```bash
git checkout -b feat/web-ui-phase-1-home-pages
```

- [ ] **Ensure FastAPI dev server is running**

```bash
uv run -m app.webapi
# Keep this process alive for the duration of Phase 1 — api:sync depends on it.
```

---

## Task 1: Extend Pydantic schemas for Phase 1 resources

**Files:**
- Modify: `app/webapi/schemas.py`

Rationale: define the response shapes up front so every subsequent endpoint task and frontend page can import stable names.

- [ ] **Step 1.1: Append new schemas to `app/webapi/schemas.py`**

Open `app/webapi/schemas.py` and append after the existing `PostRead` class:

```python
class PostDetail(PostRead):
    """Full post payload for the detail page — adds source_items blob."""

    external_id: str
    source_items: list[dict[str, Any]] | None = None


class ChannelRead(BaseModel):
    """List-page view of a channel — identifying + toggle fields only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    name: str
    description: str
    language: str
    enabled: bool
    max_posts_per_day: int
    critic_enabled: bool | None
    created_at: datetime.datetime


class ChannelSourceRead(BaseModel):
    """RSS source attached to a channel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    source_type: str
    title: str | None
    language: str | None
    enabled: bool
    relevance_score: float
    error_count: int
    last_fetched_at: datetime.datetime | None
    last_error: str | None


class ChannelDetail(ChannelRead):
    """Full channel payload — adds config + sources + recent posts summary."""

    review_chat_id: int | None
    posting_schedule: list[str] | None
    publish_schedule: list[str] | None
    footer_template: str | None
    discovery_query: str
    modified_at: datetime.datetime
    sources: list[ChannelSourceRead]
    recent_posts: list[PostRead]


class DraftBucket(BaseModel):
    """Home tile: drafts grouped by channel."""

    channel_id: int
    channel_name: str
    count: int


class ScheduledPostEntry(BaseModel):
    """Home tile: scheduled post appearing in the next 24h window."""

    post_id: int
    channel_id: int
    channel_name: str
    title: str
    scheduled_at: datetime.datetime


class ModelCostBucket(BaseModel):
    """Per-model slice of the session cost summary."""

    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    calls: int


class SessionCostSummary(BaseModel):
    """In-memory cost aggregation from app.channel.cost_tracker.

    Resets whenever the bot restarts — this is a session view, not
    persistent history. Persistent storage is Phase 1.5 scope.
    """

    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_calls: int
    session_started_at: datetime.datetime
    by_model: list[ModelCostBucket]


class HomeStats(BaseModel):
    """Aggregated response backing the home dashboard's live tiles.

    Keeps home to one round-trip; skeleton tiles are FE-only and don't
    appear here.
    """

    drafts: list[DraftBucket]
    scheduled_next_24h: list[ScheduledPostEntry]
    session_cost: SessionCostSummary
```

You will also need to add `from typing import Any` at the top of the file — verify imports.

- [ ] **Step 1.2: Verify the module imports cleanly**

```bash
uv run python -c "from app.webapi.schemas import HomeStats, ChannelDetail, PostDetail, SessionCostSummary; print('OK')"
```

Expected: `OK`.

- [ ] **Step 1.3: Commit**

```bash
git add app/webapi/schemas.py
git commit -m "feat(webapi): Phase 1 response schemas (PostDetail, ChannelDetail, HomeStats, SessionCostSummary)

Pre-declared so each following endpoint task can import a stable type."
```

---

## Task 2: `GET /api/posts/{id}` and channel filter on list

**Files:**
- Modify: `app/webapi/routes/posts.py`
- Create: `tests/webapi/test_posts.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/webapi/test_posts.py`:

```python
"""Tests for /api/posts endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    """Yield an httpx client with the webapi DB dep overridden to use the
    test session_maker."""
    from app.webapi.deps import get_session

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


async def _seed_post(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    channel_id: int = -1001,
    status: str = PostStatus.DRAFT,
    title: str = "t",
) -> int:
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=channel_id,
            external_id="ext-1",
            title=title,
            post_text="body",
            status=status,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


async def test_list_posts_filters_by_channel(
    client_factory,
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """channel_id query param narrows results to that channel only."""
    await _seed_post(db_session_maker, channel_id=-1001, title="a")
    await _seed_post(db_session_maker, channel_id=-1002, title="b")

    async with client_factory() as client:
        resp = await client.get("/api/posts", params={"channel_id": -1002})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["channel_id"] == -1002


async def test_get_post_detail_returns_full_shape(
    client_factory,
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """/api/posts/{id} returns PostDetail with external_id field present."""
    post_id = await _seed_post(db_session_maker, title="t42")

    async with client_factory() as client:
        resp = await client.get(f"/api/posts/{post_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == post_id
    assert body["title"] == "t42"
    assert "external_id" in body


async def test_get_post_detail_returns_404_when_missing(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/posts/999999")
    assert resp.status_code == 404
```

- [ ] **Step 2.2: Verify tests fail**

```bash
uv run -m pytest tests/webapi/test_posts.py -v
```

Expected: FAIL — `channel_id` query param unknown (probably 422) and `GET /api/posts/{id}` returns 404 from FastAPI routing (no such route yet).

- [ ] **Step 2.3: Implement — rewrite `app/webapi/routes/posts.py`**

Replace the full contents of `app/webapi/routes/posts.py` with:

```python
"""Channel posts — list + detail endpoints for the review panel."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChannelPost
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import PostDetail, PostRead

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[PostRead])
async def list_posts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    status: str | None = Query(default=None, description="Filter by PostStatus"),
    channel_id: int | None = Query(default=None, description="Filter by Channel.telegram_id"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChannelPost]:
    stmt = select(ChannelPost).order_by(ChannelPost.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ChannelPost.status == status)
    if channel_id is not None:
        stmt = stmt.where(ChannelPost.channel_id == channel_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelPost:
    result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    return post
```

- [ ] **Step 2.4: Verify tests pass**

```bash
uv run -m pytest tests/webapi/test_posts.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 2.5: Commit**

```bash
git add app/webapi/routes/posts.py tests/webapi/test_posts.py
git commit -m "feat(webapi): post detail endpoint + channel_id filter on list"
```

---

## Task 3: `/api/channels` router — list + detail

**Files:**
- Create: `app/webapi/routes/channels.py`
- Modify: `app/webapi/main.py` (mount the router)
- Create: `tests/webapi/test_channels.py`

- [ ] **Step 3.1: Write the failing tests**

Create `tests/webapi/test_channels.py`:

```python
"""Tests for /api/channels endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Channel, ChannelPost, ChannelSource
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


async def _seed_channel(session_maker, *, telegram_id: int = -1001, name: str = "C") -> int:
    async with session_maker() as session:
        channel = Channel(telegram_id=telegram_id, name=name, username="c")
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        return channel.id


async def test_list_channels_returns_all(
    client_factory, db_session_maker
) -> None:
    await _seed_channel(db_session_maker, telegram_id=-1001, name="A")
    await _seed_channel(db_session_maker, telegram_id=-1002, name="B")

    async with client_factory() as client:
        resp = await client.get("/api/channels")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = sorted(c["name"] for c in body)
    assert names == ["A", "B"]


async def test_get_channel_detail_includes_sources_and_posts(
    client_factory, db_session_maker
) -> None:
    ch_row_id = await _seed_channel(db_session_maker, telegram_id=-1010, name="D")

    async with db_session_maker() as session:
        session.add(ChannelSource(channel_id=-1010, url="https://x/rss", source_type="rss"))
        session.add(
            ChannelPost(channel_id=-1010, external_id="e1", title="p1", post_text="x")
        )
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/channels/{ch_row_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ch_row_id
    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"] == "https://x/rss"
    assert len(body["recent_posts"]) == 1
    assert body["recent_posts"][0]["title"] == "p1"


async def test_get_channel_detail_404_when_missing(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/channels/999999")
    assert resp.status_code == 404
```

- [ ] **Step 3.2: Verify tests fail**

```bash
uv run -m pytest tests/webapi/test_channels.py -v
```

Expected: FAIL — 404 on every path (router not mounted).

- [ ] **Step 3.3: Create the router**

Create `app/webapi/routes/channels.py`:

```python
"""Channels — list and detail endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, ChannelPost, ChannelSource
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import ChannelDetail, ChannelRead, ChannelSourceRead, PostRead

router = APIRouter(prefix="/channels", tags=["channels"])

_RECENT_POSTS_PER_CHANNEL = 10


@router.get("", response_model=list[ChannelRead])
async def list_channels(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[Channel]:
    result = await session.execute(select(Channel).order_by(Channel.name))
    return list(result.scalars().all())


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelDetail:
    channel = (
        await session.execute(select(Channel).where(Channel.id == channel_id))
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    sources_rows = (
        await session.execute(
            select(ChannelSource)
            .where(ChannelSource.channel_id == channel.telegram_id)
            .order_by(ChannelSource.enabled.desc(), ChannelSource.created_at.desc())
        )
    ).scalars().all()

    posts_rows = (
        await session.execute(
            select(ChannelPost)
            .where(ChannelPost.channel_id == channel.telegram_id)
            .order_by(ChannelPost.created_at.desc())
            .limit(_RECENT_POSTS_PER_CHANNEL)
        )
    ).scalars().all()

    return ChannelDetail(
        **ChannelRead.model_validate(channel).model_dump(),
        review_chat_id=channel.review_chat_id,
        posting_schedule=channel.posting_schedule,
        publish_schedule=channel.publish_schedule,
        footer_template=channel.footer_template,
        discovery_query=channel.discovery_query,
        modified_at=channel.modified_at,
        sources=[ChannelSourceRead.model_validate(s) for s in sources_rows],
        recent_posts=[PostRead.model_validate(p) for p in posts_rows],
    )
```

- [ ] **Step 3.4: Mount the router in `main.py`**

Edit `app/webapi/main.py`. Replace the existing `include_router` block with:

```python
from app.webapi.routes import channels, health, posts  # noqa: E402

app.include_router(health.router, prefix="/api")
app.include_router(posts.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
```

Leave CORS and factory code untouched — only the router import/mount lines change. If the factory uses a function rather than module-level app, update the equivalent section inside `create_app()`.

- [ ] **Step 3.5: Verify tests pass**

```bash
uv run -m pytest tests/webapi/test_channels.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 3.6: Commit**

```bash
git add app/webapi/routes/channels.py app/webapi/main.py tests/webapi/test_channels.py
git commit -m "feat(webapi): /api/channels list + detail (with sources + recent posts)"
```

---

## Task 4: `GET /api/costs/session`

**Files:**
- Create: `app/webapi/routes/costs.py`
- Modify: `app/webapi/main.py` (mount router)
- Create: `tests/webapi/test_costs.py`

- [ ] **Step 4.1: Write the failing tests**

Create `tests/webapi/test_costs.py`:

```python
"""Tests for /api/costs endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.channel import cost_tracker
from app.channel.cost_tracker import LLMUsage
from app.core.config import settings
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def client():
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _clean_cost_history():
    cost_tracker.reset_usage_history()
    yield
    cost_tracker.reset_usage_history()


async def test_session_cost_empty_when_no_usage(client) -> None:
    async with client as c:
        resp = await c.get("/api/costs/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["total_cost_usd"] == 0.0
    assert body["by_model"] == []


async def test_session_cost_aggregates_by_model(client) -> None:
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-a",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            timestamp=datetime.now(UTC),
        )
    )
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-a",
            input_tokens=200,
            output_tokens=100,
            cost_usd=0.02,
            timestamp=datetime.now(UTC),
        )
    )
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-b",
            input_tokens=50,
            output_tokens=25,
            cost_usd=0.005,
            timestamp=datetime.now(UTC),
        )
    )

    async with client as c:
        resp = await c.get("/api/costs/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 3
    assert pytest.approx(body["total_cost_usd"], abs=1e-6) == 0.035
    models = {b["model"]: b for b in body["by_model"]}
    assert models["m-a"]["calls"] == 2
    assert pytest.approx(models["m-a"]["cost_usd"], abs=1e-6) == 0.03
    assert models["m-b"]["calls"] == 1
```

Before writing the test, open `app/channel/cost_tracker.py` and confirm the `LLMUsage` dataclass fields match the kwargs above (`model`, `input_tokens`, `output_tokens`, `cost_usd`, `timestamp`). If the fields differ, adjust the test payload to the real shape — do not invent fields.

- [ ] **Step 4.2: Verify tests fail**

```bash
uv run -m pytest tests/webapi/test_costs.py -v
```

Expected: FAIL — 404 (router not mounted).

- [ ] **Step 4.3: Create the router**

Create `app/webapi/routes/costs.py`:

```python
"""Costs — session summary from in-memory cost_tracker."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.channel.cost_tracker import get_session_summary
from app.webapi.deps import require_super_admin
from app.webapi.schemas import ModelCostBucket, SessionCostSummary

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/session", response_model=SessionCostSummary)
async def session_cost(
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SessionCostSummary:
    summary = get_session_summary()
    buckets = [
        ModelCostBucket(
            model=model_name,
            cost_usd=float(data.get("cost", 0.0)),
            input_tokens=int(data.get("input", 0)),
            output_tokens=int(data.get("output", 0)),
            calls=int(data.get("calls", 0)),
        )
        for model_name, data in (summary.get("by_model") or {}).items()
    ]
    return SessionCostSummary(
        total_cost_usd=float(summary.get("total_cost_usd", 0.0)),
        total_input_tokens=int(summary.get("total_input_tokens", 0)),
        total_output_tokens=int(summary.get("total_output_tokens", 0)),
        total_calls=int(summary.get("total_calls", 0)),
        session_started_at=summary["session_started_at"],
        by_model=buckets,
    )
```

Before writing this, open `app/channel/cost_tracker.py:215` and confirm the exact shape of `get_session_summary()`'s return. If the keys differ from what this code expects (`total_cost_usd`, `total_input_tokens`, `total_output_tokens`, `total_calls`, `session_started_at`, `by_model`), update the mapping — do not invent fields. When the returned dict has no `session_started_at`, fall back to `utc_now()` from `app.core.time` rather than crashing.

- [ ] **Step 4.4: Mount the router**

Edit `app/webapi/main.py` — extend the imports and mount calls:

```python
from app.webapi.routes import channels, costs, health, posts

app.include_router(health.router, prefix="/api")
app.include_router(posts.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(costs.router, prefix="/api")
```

- [ ] **Step 4.5: Verify tests pass**

```bash
uv run -m pytest tests/webapi/test_costs.py -v
```

Expected: PASS (2 tests). If the `get_session_summary()` shape differed from the assumed keys, the test will surface the mismatch — fix the mapping in `costs.py` to match reality (not the tests to match the bug).

- [ ] **Step 4.6: Commit**

```bash
git add app/webapi/routes/costs.py app/webapi/main.py tests/webapi/test_costs.py
git commit -m "feat(webapi): /api/costs/session — in-memory LLM usage summary"
```

---

## Task 5: `GET /api/stats/home` aggregator

**Files:**
- Create: `app/webapi/routes/stats.py`
- Modify: `app/webapi/main.py` (mount router)
- Create: `tests/webapi/test_stats.py`

- [ ] **Step 5.1: Write the failing test**

Create `tests/webapi/test_stats.py`:

```python
"""Tests for /api/stats endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.channel import cost_tracker
from app.core.config import settings
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import Channel, ChannelPost
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _clean_cost_history():
    cost_tracker.reset_usage_history()
    yield
    cost_tracker.reset_usage_history()


async def test_home_stats_shape(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-1001, name="A", username="a"))
        session.add(
            ChannelPost(
                channel_id=-1001,
                external_id="e-draft",
                title="draft post",
                post_text="x",
                status=PostStatus.DRAFT,
            )
        )
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    assert resp.status_code == 200
    body = resp.json()
    assert "drafts" in body and "scheduled_next_24h" in body and "session_cost" in body
    assert any(d["channel_id"] == -1001 and d["count"] >= 1 for d in body["drafts"])


async def test_home_stats_scheduled_window_is_24h(
    client_factory, db_session_maker
) -> None:
    now = utc_now()
    far_future = now + datetime.timedelta(days=3)
    soon = now + datetime.timedelta(hours=6)

    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-1002, name="B", username="b"))
        post_far = ChannelPost(
            channel_id=-1002,
            external_id="far",
            title="far",
            post_text="x",
            status=PostStatus.SCHEDULED,
        )
        post_far.scheduled_at = far_future
        post_soon = ChannelPost(
            channel_id=-1002,
            external_id="soon",
            title="soon",
            post_text="x",
            status=PostStatus.SCHEDULED,
        )
        post_soon.scheduled_at = soon
        session.add(post_far)
        session.add(post_soon)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    titles = [e["title"] for e in resp.json()["scheduled_next_24h"]]
    assert "soon" in titles
    assert "far" not in titles
```

- [ ] **Step 5.2: Verify tests fail**

```bash
uv run -m pytest tests/webapi/test_stats.py -v
```

Expected: FAIL — 404.

- [ ] **Step 5.3: Create the router**

Create `app/webapi/routes/stats.py`:

```python
"""Home dashboard aggregator."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.cost_tracker import get_session_summary
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import Channel, ChannelPost
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import (
    DraftBucket,
    HomeStats,
    ModelCostBucket,
    ScheduledPostEntry,
    SessionCostSummary,
)

router = APIRouter(prefix="/stats", tags=["stats"])

_SCHEDULED_WINDOW_HOURS = 24


@router.get("/home", response_model=HomeStats)
async def home_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> HomeStats:
    drafts_rows = (
        await session.execute(
            select(
                ChannelPost.channel_id,
                Channel.name,
                func.count(ChannelPost.id).label("count"),
            )
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.status == PostStatus.DRAFT)
            .group_by(ChannelPost.channel_id, Channel.name)
            .order_by(func.count(ChannelPost.id).desc())
        )
    ).all()
    drafts = [
        DraftBucket(
            channel_id=row.channel_id,
            channel_name=row.name or f"#{row.channel_id}",
            count=int(row.count),
        )
        for row in drafts_rows
    ]

    now = utc_now()
    horizon = now + datetime.timedelta(hours=_SCHEDULED_WINDOW_HOURS)
    scheduled_rows = (
        await session.execute(
            select(ChannelPost, Channel.name)
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.scheduled_at.is_not(None))
            .where(ChannelPost.scheduled_at >= now)
            .where(ChannelPost.scheduled_at <= horizon)
            .order_by(ChannelPost.scheduled_at.asc())
        )
    ).all()
    scheduled = [
        ScheduledPostEntry(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_name=ch_name or f"#{post.channel_id}",
            title=post.title,
            scheduled_at=post.scheduled_at,
        )
        for post, ch_name in scheduled_rows
    ]

    summary = get_session_summary()
    buckets = [
        ModelCostBucket(
            model=model_name,
            cost_usd=float(data.get("cost", 0.0)),
            input_tokens=int(data.get("input", 0)),
            output_tokens=int(data.get("output", 0)),
            calls=int(data.get("calls", 0)),
        )
        for model_name, data in (summary.get("by_model") or {}).items()
    ]
    session_cost = SessionCostSummary(
        total_cost_usd=float(summary.get("total_cost_usd", 0.0)),
        total_input_tokens=int(summary.get("total_input_tokens", 0)),
        total_output_tokens=int(summary.get("total_output_tokens", 0)),
        total_calls=int(summary.get("total_calls", 0)),
        session_started_at=summary.get("session_started_at", now),
        by_model=buckets,
    )

    return HomeStats(
        drafts=drafts,
        scheduled_next_24h=scheduled,
        session_cost=session_cost,
    )
```

If `get_session_summary()` returns different keys than what this file expects, mirror the mapping fix you made in Task 4 here — both endpoints must agree on the shape.

- [ ] **Step 5.4: Mount the router**

Extend `app/webapi/main.py`:

```python
from app.webapi.routes import channels, costs, health, posts, stats

app.include_router(health.router, prefix="/api")
app.include_router(posts.router, prefix="/api")
app.include_router(channels.router, prefix="/api")
app.include_router(costs.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
```

- [ ] **Step 5.5: Verify tests pass**

```bash
uv run -m pytest tests/webapi/test_stats.py -v
```

Expected: PASS.

- [ ] **Step 5.6: Commit**

```bash
git add app/webapi/routes/stats.py app/webapi/main.py tests/webapi/test_stats.py
git commit -m "feat(webapi): /api/stats/home aggregator for home-tile data

One round-trip covers drafts-by-channel, next-24h scheduled posts, and
the in-memory session cost summary."
```

---

## Task 6: Regenerate OpenAPI → TS types

**Files:**
- Modify: `webui/src/lib/api/types.ts` (regenerated)

- [ ] **Step 6.1: Ensure FastAPI dev server has reloaded with the new routes**

```bash
/usr/bin/curl -s http://127.0.0.1:8787/api/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(sorted(d['paths'].keys()))"
```

Expected output must contain each of:
`/api/posts`, `/api/posts/{post_id}`, `/api/channels`, `/api/channels/{channel_id}`, `/api/costs/session`, `/api/stats/home`.

If any path is missing, the dev server didn't reload — restart it before proceeding.

- [ ] **Step 6.2: Regenerate types**

```bash
pnpm --dir webui run api:sync
```

- [ ] **Step 6.3: Verify the generated file covers the new schemas**

```bash
grep -E 'HomeStats|ChannelDetail|PostDetail|SessionCostSummary|DraftBucket' webui/src/lib/api/types.ts | head -6
```

Expected: each type name appears at least once.

- [ ] **Step 6.4: Svelte check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 6.5: Commit**

```bash
git add webui/src/lib/api/types.ts
git commit -m "chore(webui): regenerate OpenAPI types after Phase 1 endpoints"
```

---

## Task 7: `useLivePoll` hook + tile primitives

**Files:**
- Create: `webui/src/lib/hooks/useLivePoll.ts`
- Create: `webui/src/lib/components/home/Tile.svelte`
- Create: `webui/src/lib/components/home/StatTile.svelte`
- Create: `webui/src/lib/components/home/ListTile.svelte`
- Create: `webui/src/lib/components/home/SkeletonTile.svelte`

- [ ] **Step 7.1: Create `useLivePoll`**

Create `webui/src/lib/hooks/useLivePoll.ts`:

```typescript
import type { ApiResult } from '$lib/api/client';
import { apiFetch } from '$lib/api/client';

type State<T> = {
	data: T | null;
	error: string | null;
	loading: boolean;
	lastUpdatedAt: Date | null;
	refresh: () => Promise<void>;
};

/**
 * Reactive polling hook. Returns $state-wrapped view; call `refresh()` for
 * a manual re-fetch. Starts immediately, polls every `intervalMs` (default
 * 30s), and cleans up its timer when the using component unmounts.
 */
export function useLivePoll<T>(path: string, intervalMs = 30_000): State<T> {
	const view = $state<State<T>>({
		data: null,
		error: null,
		loading: true,
		lastUpdatedAt: null,
		refresh: async () => {
			await run();
		}
	});

	async function run() {
		const res: ApiResult<T> = await apiFetch<T>(path);
		if (res.error) {
			view.error = res.error.message;
			view.data = null;
		} else {
			view.data = res.data;
			view.error = null;
			view.lastUpdatedAt = new Date();
		}
		view.loading = false;
	}

	$effect(() => {
		void run();
		const id = setInterval(run, intervalMs);
		return () => clearInterval(id);
	});

	return view;
}
```

- [ ] **Step 7.2: Create `Tile.svelte` (base shell)**

Create `webui/src/lib/components/home/Tile.svelte`:

```svelte
<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import type { Snippet } from 'svelte';

	type Props = { title: string; children: Snippet; action?: Snippet };
	let { title, children, action }: Props = $props();
</script>

<Card.Root class="h-full">
	<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
		<Card.Title class="text-sm font-medium text-zinc-700">{title}</Card.Title>
		{#if action}{@render action()}{/if}
	</Card.Header>
	<Card.Content>
		{@render children()}
	</Card.Content>
</Card.Root>
```

- [ ] **Step 7.3: Create `StatTile.svelte` (big-number variant)**

Create `webui/src/lib/components/home/StatTile.svelte`:

```svelte
<script lang="ts">
	import Tile from './Tile.svelte';

	type Props = { title: string; value: string | number; caption?: string };
	let { title, value, caption }: Props = $props();
</script>

<Tile {title}>
	<div class="text-2xl font-semibold tracking-tight text-zinc-900">{value}</div>
	{#if caption}
		<p class="mt-1 text-xs text-zinc-500">{caption}</p>
	{/if}
</Tile>
```

- [ ] **Step 7.4: Create `ListTile.svelte`**

Create `webui/src/lib/components/home/ListTile.svelte`. Keep it non-generic — the caller maps its data to `{primary, secondary}` items before passing in. Simpler type story, no Svelte-5 generic-on-props landmines:

```svelte
<script lang="ts">
	import Tile from './Tile.svelte';

	type Line = { primary: string; secondary?: string };
	type Props = { title: string; items: Line[]; empty: string };
	let { title, items, empty }: Props = $props();
</script>

<Tile {title}>
	{#if items.length === 0}
		<p class="text-xs text-zinc-500">{empty}</p>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each items as item, i (i)}
				<li class="flex items-baseline justify-between text-sm">
					<span class="truncate text-zinc-800">{item.primary}</span>
					{#if item.secondary}
						<span class="ml-2 shrink-0 text-xs text-zinc-500">{item.secondary}</span>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</Tile>
```

- [ ] **Step 7.5: Create `SkeletonTile.svelte`**

Create `webui/src/lib/components/home/SkeletonTile.svelte`:

```svelte
<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import Tile from './Tile.svelte';

	type Props = { title: string; phase: number; hint?: string };
	let { title, phase, hint }: Props = $props();
</script>

<Tile {title}>
	{#snippet action()}
		<Badge variant="secondary" class="text-[10px]">P{phase}</Badge>
	{/snippet}
	<p class="text-xs text-zinc-500">{hint ?? 'Coming in Phase ' + phase + '.'}</p>
</Tile>
```

- [ ] **Step 7.6: Verify type-check**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`. If `useLivePoll` triggers "effect outside component" warnings, make sure the file is imported only from `.svelte` files (Svelte 5 requires runes to run inside a Svelte reactive context) — the hook is designed to be called from `+page.svelte` top-level.

- [ ] **Step 7.7: Commit**

```bash
git add webui/src/lib/hooks webui/src/lib/components/home
git commit -m "feat(webui): tile primitives + useLivePoll hook

Tile / StatTile / ListTile / SkeletonTile for dashboards, plus a 30s
polling hook used by the home page."
```

---

## Task 8: Home dashboard — 8-tile grid

**Files:**
- Modify: `webui/src/routes/+page.svelte`

- [ ] **Step 8.1: Replace `+page.svelte` with the live home**

Replace the contents of `webui/src/routes/+page.svelte` with:

```svelte
<script lang="ts">
	import ListTile from '$lib/components/home/ListTile.svelte';
	import SkeletonTile from '$lib/components/home/SkeletonTile.svelte';
	import StatTile from '$lib/components/home/StatTile.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];

	const stats = useLivePoll<HomeStats>('/api/stats/home');

	const totalDrafts = $derived(
		stats.data?.drafts.reduce((acc, d) => acc + d.count, 0) ?? 0
	);
	const weekCostUsd = $derived(stats.data?.session_cost.total_cost_usd ?? 0);

	function fmtMoney(usd: number): string {
		return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(2)}`;
	}

	function fmtWhen(iso: string): string {
		const d = new Date(iso);
		const hh = d.getHours().toString().padStart(2, '0');
		const mm = d.getMinutes().toString().padStart(2, '0');
		return `${hh}:${mm}`;
	}
</script>

<div class="space-y-6 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Home dashboard</h2>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if stats.error}
				<span class="text-red-600">Error: {stats.error}</span>
			{:else if stats.lastUpdatedAt}
				<span>Updated {stats.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<button
				type="button"
				class="rounded-md border border-zinc-200 px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => stats.refresh()}
			>
				Refresh
			</button>
		</div>
	</header>

	<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
		<StatTile
			title="Drafts queue"
			value={totalDrafts}
			caption={stats.loading ? 'loading…' : `${stats.data?.drafts.length ?? 0} channels`}
		/>
		<ListTile
			title="Scheduled next 24h"
			items={(stats.data?.scheduled_next_24h ?? []).map((p) => ({
				primary: p.title,
				secondary: fmtWhen(p.scheduled_at)
			}))}
			empty={stats.loading ? 'loading…' : 'Nothing scheduled'}
		/>
		<StatTile
			title="LLM cost (session)"
			value={fmtMoney(weekCostUsd)}
			caption="Since last bot restart"
		/>
		<SkeletonTile title="Post views" phase={2} hint="Requires Telethon aggregation." />
		<SkeletonTile title="Chats heatmap" phase={2} hint="Requires Telethon aggregation." />
		<SkeletonTile title="Members delta" phase={2} hint="Requires Telethon aggregation." />
		<SkeletonTile title="Spam pings" phase={3} hint="Needs spam detector." />
		<SkeletonTile title="Chat graph" phase={3} hint="Needs relationship model." />
	</div>
</div>
```

- [ ] **Step 8.2: Visual verify**

With dev servers running, open `/` in your browser. Confirm:
- Grid of 8 tiles renders (3 live + 5 P2/P3 skeletons)
- "Drafts queue" shows a number (could be 0)
- "Scheduled next 24h" lists real scheduled posts or "Nothing scheduled"
- "LLM cost (session)" shows a dollar amount (likely `<$0.01` if the bot hasn't run)
- Clicking "Refresh" triggers a fresh fetch (no visible change if data same, but no error)
- No 403/500 in network tab

If the endpoint returns 503, the `.env` is missing `ADMIN_SUPER_ADMINS`; flag and stop.

- [ ] **Step 8.3: Commit**

```bash
git add webui/src/routes/+page.svelte
git commit -m "feat(webui): home dashboard with 8 tiles (3 live via /api/stats/home)"
```

---

## Task 9: `/posts` list page with filters

**Files:**
- Modify: `webui/src/routes/posts/+page.svelte`

- [ ] **Step 9.1: Replace the skeleton with the real list**

Replace `webui/src/routes/posts/+page.svelte`:

```svelte
<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type Post = components['schemas']['PostRead'];

	let status = $state<string>('');
	let channelId = $state<string>('');
	let posts = $state<Post[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function load() {
		loading = true;
		error = null;
		const params = new URLSearchParams({ limit: '100' });
		if (status) params.set('status', status);
		if (channelId) params.set('channel_id', channelId);
		const res = await apiFetch<Post[]>(`/api/posts?${params}`);
		if (res.error) {
			error = res.error.message;
			posts = [];
		} else {
			posts = res.data;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	const STATUSES = ['draft', 'sent_for_review', 'approved', 'scheduled', 'published', 'rejected', 'failed', 'deleted'];
</script>

<div class="space-y-4 px-6 py-6">
	<header class="flex items-center justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Posts</h2>
		<div class="flex items-center gap-2">
			<select
				bind:value={status}
				class="rounded-md border border-zinc-200 bg-white px-2 py-1 text-sm"
				onchange={() => load()}
			>
				<option value="">all statuses</option>
				{#each STATUSES as s (s)}<option value={s}>{s}</option>{/each}
			</select>
			<Input
				placeholder="channel_id"
				bind:value={channelId}
				class="w-40"
				onkeydown={(e: KeyboardEvent) => {
					if (e.key === 'Enter') load();
				}}
			/>
		</div>
	</header>

	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if posts.length === 0}
		<p class="text-sm text-zinc-500">No posts match these filters.</p>
	{:else}
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head class="w-16">ID</Table.Head>
					<Table.Head class="w-32">Status</Table.Head>
					<Table.Head>Title</Table.Head>
					<Table.Head class="w-32">Channel</Table.Head>
					<Table.Head class="w-40">Created</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each posts as p (p.id)}
					<Table.Row>
						<Table.Cell class="text-zinc-500">{p.id}</Table.Cell>
						<Table.Cell><Badge variant="secondary">{p.status}</Badge></Table.Cell>
						<Table.Cell class="truncate">
							<a class="text-zinc-900 hover:underline" href={`/posts/${p.id}`}>{p.title}</a>
						</Table.Cell>
						<Table.Cell class="font-mono text-xs text-zinc-600">{p.channel_id}</Table.Cell>
						<Table.Cell class="text-xs text-zinc-500">
							{new Date(p.created_at).toLocaleString()}
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{/if}
</div>
```

- [ ] **Step 9.2: Type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS`. If the `components['schemas']['PostRead']` import fails, Task 6 didn't regenerate correctly — re-run it.

- [ ] **Step 9.3: Smoke test**

Open `/posts` in the browser. Confirm:
- Table renders with recent posts (or "No posts match")
- Status dropdown filters reloads
- Clicking a title navigates to `/posts/:id` (which currently returns a blank page — next task fills it)

- [ ] **Step 9.4: Commit**

```bash
git add webui/src/routes/posts/+page.svelte
git commit -m "feat(webui): /posts list page with status + channel_id filters"
```

---

## Task 10: `/posts/:id` detail page

**Files:**
- Modify: `webui/src/routes/posts/[id]/+page.svelte`

- [ ] **Step 10.1: Replace skeleton with detail view**

Replace `webui/src/routes/posts/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type PostDetail = components['schemas']['PostDetail'];

	let post = $state<PostDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const postId = $derived(page.params.id);

	async function load() {
		loading = true;
		const res = await apiFetch<PostDetail>(`/api/posts/${postId}`);
		if (res.error) {
			error = res.error.message;
			post = null;
		} else {
			post = res.data;
			error = null;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	function stub(action: string) {
		alert(`"${action}" will land in Phase 4. For now, use Telegram.`);
	}
</script>

<div class="mx-auto max-w-3xl space-y-4 px-6 py-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if post}
		<header class="flex items-start justify-between gap-4">
			<div>
				<div class="flex items-center gap-2 text-xs text-zinc-500">
					<a href="/posts" class="hover:underline">Posts</a>
					<span>›</span>
					<span class="font-mono">#{post.id}</span>
				</div>
				<h2 class="mt-1 text-xl font-semibold tracking-tight">{post.title}</h2>
				<div class="mt-2 flex items-center gap-2">
					<Badge variant="secondary">{post.status}</Badge>
					{#if post.source_url}
						<a href={post.source_url} target="_blank" rel="noreferrer" class="text-xs text-blue-600 hover:underline">Source</a>
					{/if}
				</div>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<Button variant="outline" size="sm" onclick={() => stub('approve')}>Approve</Button>
				<Button variant="outline" size="sm" onclick={() => stub('reject')}>Reject</Button>
				<Button variant="outline" size="sm" onclick={() => stub('edit')}>Edit</Button>
			</div>
		</header>

		<Card.Root>
			<Card.Header><Card.Title>Body</Card.Title></Card.Header>
			<Card.Content>
				<pre class="whitespace-pre-wrap font-sans text-sm leading-6 text-zinc-800">{post.post_text}</pre>
			</Card.Content>
		</Card.Root>

		{#if post.image_urls && post.image_urls.length > 0}
			<Card.Root>
				<Card.Header><Card.Title>Images ({post.image_urls.length})</Card.Title></Card.Header>
				<Card.Content>
					<div class="grid grid-cols-2 gap-3 md:grid-cols-3">
						{#each post.image_urls as url (url)}
							<img src={url} alt="" class="h-32 w-full rounded-md object-cover" loading="lazy" />
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
```

- [ ] **Step 10.2: Smoke test**

Click a post from `/posts`. Confirm:
- Title, status, body render
- Stub buttons pop an alert
- Images grid appears if the post has images
- Bad id (`/posts/9999999`) shows an "Error: Post 9999999 not found" message, not a blank page

- [ ] **Step 10.3: Commit**

```bash
git add webui/src/routes/posts/[id]/+page.svelte
git commit -m "feat(webui): /posts/:id detail view with stubbed action buttons"
```

---

## Task 11: `/channels` list page

**Files:**
- Modify: `webui/src/routes/channels/+page.svelte`

- [ ] **Step 11.1: Replace skeleton**

Replace `webui/src/routes/channels/+page.svelte`:

```svelte
<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type Channel = components['schemas']['ChannelRead'];

	let channels = $state<Channel[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		void (async () => {
			const res = await apiFetch<Channel[]>('/api/channels');
			if (res.error) {
				error = res.error.message;
			} else {
				channels = res.data;
			}
			loading = false;
		})();
	});
</script>

<div class="space-y-4 px-6 py-6">
	<h2 class="text-lg font-semibold tracking-tight">Channels</h2>
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else}
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head>Name</Table.Head>
					<Table.Head class="w-32">Language</Table.Head>
					<Table.Head class="w-32">Enabled</Table.Head>
					<Table.Head class="w-32">Posts/day</Table.Head>
					<Table.Head class="w-40">Telegram ID</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each channels as c (c.id)}
					<Table.Row>
						<Table.Cell>
							<a href={`/channels/${c.id}`} class="font-medium text-zinc-900 hover:underline">{c.name}</a>
							{#if c.username}
								<span class="ml-1 text-xs text-zinc-500">@{c.username}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="text-xs uppercase text-zinc-600">{c.language}</Table.Cell>
						<Table.Cell>
							{#if c.enabled}<Badge>on</Badge>{:else}<Badge variant="secondary">off</Badge>{/if}
						</Table.Cell>
						<Table.Cell class="text-sm text-zinc-700">{c.max_posts_per_day}</Table.Cell>
						<Table.Cell class="font-mono text-xs text-zinc-600">{c.telegram_id}</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{/if}
</div>
```

- [ ] **Step 11.2: Type-check + smoke test**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS`. Open `/channels` in browser — see real channel rows.

- [ ] **Step 11.3: Commit**

```bash
git add webui/src/routes/channels/+page.svelte
git commit -m "feat(webui): /channels list page"
```

---

## Task 12: `/channels/:id` detail page

**Files:**
- Modify: `webui/src/routes/channels/[id]/+page.svelte`

- [ ] **Step 12.1: Replace skeleton**

Replace `webui/src/routes/channels/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type ChannelDetail = components['schemas']['ChannelDetail'];

	let channel = $state<ChannelDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const channelId = $derived(page.params.id);

	$effect(() => {
		void (async () => {
			loading = true;
			const res = await apiFetch<ChannelDetail>(`/api/channels/${channelId}`);
			if (res.error) {
				error = res.error.message;
				channel = null;
			} else {
				channel = res.data;
				error = null;
			}
			loading = false;
		})();
	});
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if channel}
		<header>
			<div class="text-xs text-zinc-500">
				<a href="/channels" class="hover:underline">Channels</a> › <span class="font-mono">#{channel.id}</span>
			</div>
			<h2 class="mt-1 text-xl font-semibold tracking-tight">{channel.name}</h2>
			<p class="mt-1 text-sm text-zinc-600">{channel.description || '—'}</p>
		</header>

		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Config</Card.Title></Card.Header>
				<Card.Content class="space-y-2 text-sm">
					<div>Telegram ID: <span class="font-mono">{channel.telegram_id}</span></div>
					<div>Language: <span class="uppercase">{channel.language}</span></div>
					<div>Enabled: {channel.enabled ? 'yes' : 'no'}</div>
					<div>Max posts/day: {channel.max_posts_per_day}</div>
					<div>Review chat: <span class="font-mono">{channel.review_chat_id ?? '—'}</span></div>
					<div>Posting schedule: {channel.posting_schedule?.join(', ') ?? '—'}</div>
					<div>Publish schedule: {channel.publish_schedule?.join(', ') ?? '—'}</div>
					<div>Critic: {channel.critic_enabled ?? 'inherit'}</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Sources ({channel.sources.length})</Card.Title></Card.Header>
				<Card.Content>
					{#if channel.sources.length === 0}
						<p class="text-sm text-zinc-500">No sources configured.</p>
					{:else}
						<ul class="flex flex-col gap-2 text-sm">
							{#each channel.sources as s (s.id)}
								<li class="flex items-center justify-between gap-2">
									<span class="truncate" title={s.url}>{s.title ?? s.url}</span>
									<span class="shrink-0">
										{#if s.enabled}<Badge class="text-[10px]">on</Badge>{:else}<Badge variant="secondary" class="text-[10px]">off</Badge>{/if}
										{#if s.error_count > 0}<Badge variant="destructive" class="text-[10px]">err×{s.error_count}</Badge>{/if}
									</span>
								</li>
							{/each}
						</ul>
					{/if}
				</Card.Content>
			</Card.Root>
		</div>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Recent posts ({channel.recent_posts.length})</Card.Title></Card.Header>
			<Card.Content>
				{#if channel.recent_posts.length === 0}
					<p class="text-sm text-zinc-500">No posts yet.</p>
				{:else}
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head class="w-28">Status</Table.Head>
								<Table.Head>Title</Table.Head>
								<Table.Head class="w-40">Created</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each channel.recent_posts as p (p.id)}
								<Table.Row>
									<Table.Cell><Badge variant="secondary">{p.status}</Badge></Table.Cell>
									<Table.Cell><a href={`/posts/${p.id}`} class="hover:underline">{p.title}</a></Table.Cell>
									<Table.Cell class="text-xs text-zinc-500">{new Date(p.created_at).toLocaleString()}</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
```

- [ ] **Step 12.2: Smoke test**

Click a channel name on `/channels`. Detail renders with config card, sources card, and recent posts table.

- [ ] **Step 12.3: Commit**

```bash
git add webui/src/routes/channels/[id]/+page.svelte
git commit -m "feat(webui): /channels/:id detail with config, sources, recent posts"
```

---

## Task 13: `/costs` page (session summary)

**Files:**
- Modify: `webui/src/routes/costs/+page.svelte`

- [ ] **Step 13.1: Replace skeleton**

Replace `webui/src/routes/costs/+page.svelte`:

```svelte
<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll';
	import type { components } from '$lib/api/types';

	type Summary = components['schemas']['SessionCostSummary'];

	const cost = useLivePoll<Summary>('/api/costs/session', 60_000);

	function fmt(usd: number): string {
		return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(4)}`;
	}
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Costs</h2>
		{#if cost.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {cost.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	<Card.Root>
		<Card.Header>
			<Card.Title class="text-sm">Session summary</Card.Title>
			<p class="text-xs text-zinc-500">
				In-memory aggregation from <code>cost_tracker</code>. Resets on bot restart — persistent history is Phase 1.5.
			</p>
		</Card.Header>
		<Card.Content class="space-y-1 text-sm">
			{#if cost.loading}
				<p class="text-zinc-500">Loading…</p>
			{:else if cost.error}
				<p class="text-red-600">Error: {cost.error}</p>
			{:else if cost.data}
				<div>Total cost: <strong>{fmt(cost.data.total_cost_usd)}</strong></div>
				<div>Total calls: {cost.data.total_calls}</div>
				<div>Input tokens: {cost.data.total_input_tokens.toLocaleString()}</div>
				<div>Output tokens: {cost.data.total_output_tokens.toLocaleString()}</div>
				<div class="text-xs text-zinc-500">Session started at {new Date(cost.data.session_started_at).toLocaleString()}</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header><Card.Title class="text-sm">Breakdown by model</Card.Title></Card.Header>
		<Card.Content>
			{#if !cost.data || cost.data.by_model.length === 0}
				<p class="text-sm text-zinc-500">No usage yet this session.</p>
			{:else}
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Model</Table.Head>
							<Table.Head class="w-28">Calls</Table.Head>
							<Table.Head class="w-32">Input tokens</Table.Head>
							<Table.Head class="w-32">Output tokens</Table.Head>
							<Table.Head class="w-32">Cost</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each cost.data.by_model as b (b.model)}
							<Table.Row>
								<Table.Cell class="font-mono text-xs">{b.model}</Table.Cell>
								<Table.Cell>{b.calls}</Table.Cell>
								<Table.Cell>{b.input_tokens.toLocaleString()}</Table.Cell>
								<Table.Cell>{b.output_tokens.toLocaleString()}</Table.Cell>
								<Table.Cell>{fmt(b.cost_usd)}</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
```

- [ ] **Step 13.2: Type-check + smoke test**

```bash
pnpm --dir webui run check
```

Open `/costs`. Expect the two cards (Session summary + Breakdown) — likely both mostly empty if the bot hasn't run since restart, that's fine.

- [ ] **Step 13.3: Commit**

```bash
git add webui/src/routes/costs/+page.svelte
git commit -m "feat(webui): /costs page with session summary + model breakdown"
```

---

## Task 14: End-to-end verification + PR

- [ ] **Step 14.1: Full backend test run**

```bash
uv run -m pytest -x
```

Expected: all tests pass, including the 11 new Phase 1 tests (2 from Phase 0 + 9 new).

- [ ] **Step 14.2: Lint / format / type**

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run ty check app/webapi tests/webapi
pnpm --dir webui run check
```

All clean.

- [ ] **Step 14.3: Click-through**

With both dev servers running, walk each page:
- `/` — 8 tiles, 3 with data, 5 P2/P3 skeletons, refresh works
- `/posts` — table with filters
- `/posts/:id` — click a row, detail renders, stub buttons pop alerts
- `/channels` — list
- `/channels/:id` — config / sources / recent posts cards
- `/costs` — session summary (probably mostly empty)

All pages return 200; no console errors in browser.

- [ ] **Step 14.4: Push and open PR**

```bash
git push -u origin feat/web-ui-phase-1-home-pages
gh pr create --title "feat(webui): Phase 1 — home dashboard + posts/channels/costs pages" --body "$(cat <<'EOF'
## Summary
- `/api/stats/home` aggregator for home-tile data (drafts by channel, scheduled next 24h, session cost summary)
- `/api/posts/{id}` detail + `channel_id` filter on list
- `/api/channels` list + `/api/channels/{id}` detail (includes sources + recent 10 posts)
- `/api/costs/session` in-memory summary from `cost_tracker`
- Home dashboard (`/`) with 8 tiles: 3 live, 5 Phase 2/3 skeletons
- `/posts` filterable table + `/posts/:id` detail view (approve/reject/edit are Phase-4 stubs)
- `/channels` list + `/channels/:id` detail
- `/costs` session summary + model breakdown
- `useLivePoll` hook (30s default, manual refresh) and tile primitives (Tile/StatTile/ListTile/SkeletonTile)

## Scope note
Persistent cost history is **Phase 1.5**, not Phase 1 — `cost_tracker` is in-memory. The home tile and `/costs` page both label this clearly as "Session / since last bot restart".

## Test plan
- [x] `uv run -m pytest` — new tests cover posts (list filter + detail + 404), channels (list + detail), costs, and the home aggregator
- [x] ruff + ty clean
- [x] svelte-check 0 errors
- [x] Manual click-through of all 5 pages + home

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Done

Phase 1 complete. Home has real tiles, Posts/Channels/Costs read from the DB, mutations remain stubbed. Phase 2 picks this up by adding Telethon aggregations for the 3 P2 tiles on home.
