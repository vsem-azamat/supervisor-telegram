# Phase 4b — Posts Mutations Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development.

**Goal:** Replace the stub `alert()` buttons in `/posts/[id]` with working Approve / Reject / Edit text mutations. The review service layer already exists (`app/channel/review/service.py`) — this phase adds: (1) a webapi-owned `Bot` HTTP client for outgoing Telegram calls, (2) three POST/PATCH endpoints, (3) UI wiring with optimistic state + toast feedback.

**Architecture:**
- The webapi process does NOT share memory with the bot process (separate uvicorn). To publish, webapi instantiates its own `aiogram.Bot(token=…)` and calls `app.channel.publisher.publish_post(bot, …)` directly. This is safe — `Bot` is just an HTTP client to Telegram, not a polling daemon. The dispatcher (which would conflict) is never created here.
- Approve / reject reuse `approve_post` / `reject_post` from `app/channel/review/service.py` (no fork).
- Edit-text gets a new direct setter `set_post_text(post_id, new_text, session_maker)` — verbatim write, no LLM. Distinct from the existing LLM-rewrite `edit_post_text`.
- Bot lifecycle: created in `_lifespan` startup, closed in shutdown. Stored on `app.state.publish_bot`.

**Tech Stack:** FastAPI, aiogram 3.x, SQLAlchemy 2.x async, SvelteKit 2 + Svelte 5 runes, svelte-sonner toasts.

---

## File Structure

| Path | Purpose |
|---|---|
| `app/webapi/services/publish_bot.py` | Build / close webapi-owned `Bot` instance |
| `app/webapi/main.py` | Wire `publish_bot` into `_lifespan` |
| `app/webapi/deps.py` | `get_publish_bot` FastAPI dep |
| `app/channel/review/service.py` | Add `set_post_text` (verbatim setter, no LLM) |
| `app/webapi/routes/posts.py` | `POST /{id}/approve`, `POST /{id}/reject`, `PATCH /{id}/text` |
| `app/webapi/schemas.py` | `PostMutationResponse`, `PostTextEdit` |
| `webui/src/lib/api/types.ts` | Auto-regen |
| `webui/src/routes/posts/[id]/+page.svelte` | Replace `stub()` calls with real wiring |
| `tests/unit/test_set_post_text.py` | Service-level coverage |
| `tests/webapi/test_post_mutations.py` | Endpoint coverage with stub publish_bot |

---

## Tasks

### Task 1 — `set_post_text` service function

**Files:**
- Modify: `app/channel/review/service.py`
- Create: `tests/unit/test_set_post_text.py`

- [ ] **Step 1** — Append after `delete_post` (around line 328):

```python
async def set_post_text(
    post_id: int,
    new_text: str,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Verbatim text replacement. Distinct from ``edit_post_text`` (LLM rewrite).

    Used by the web UI when an admin edits the post in a textarea. No
    re-embedding (text changes don't re-run dedup; the original embedding
    stays attached to the source-item identity).
    """
    from sqlalchemy import select

    if not new_text.strip():
        return "Post text cannot be empty."

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if post is None:
            return "Post not found."
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot edit."
        if post.status == PostStatus.REJECTED:
            return "Post was rejected — cannot edit."
        if post.status == PostStatus.SKIPPED:
            return "Post was skipped — cannot edit."

        post.post_text = new_text
        await session.commit()
        logger.info("post_text_set", post_id=post_id, length=len(new_text))
        return "Post text updated."
```

- [ ] **Step 2** — Test:

```python
"""Service: set_post_text (verbatim text replacement)."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.channel.review.service import set_post_text
from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, *, status: PostStatus = PostStatus.DRAFT) -> int:
    ch = Channel(name="ch", language="en", telegram_id=-100100)
    session.add(ch)
    await session.flush()
    post = ChannelPost(
        channel_id=ch.telegram_id,
        external_id="x" * 16,
        title="t",
        post_text="original",
        status=status,
    )
    session.add(post)
    await session.commit()
    return post.id


async def test_updates_text(session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    post_id = await _seed(session)
    msg = await set_post_text(post_id, "new text", db_session_maker)
    assert "updated" in msg.lower()


async def test_rejects_empty_text(session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    post_id = await _seed(session)
    msg = await set_post_text(post_id, "  ", db_session_maker)
    assert "empty" in msg.lower()


async def test_blocks_edit_after_publish(session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    post_id = await _seed(session, status=PostStatus.APPROVED)
    msg = await set_post_text(post_id, "new", db_session_maker)
    assert "Already published" in msg
```

Note: `Channel` constructor signature might differ — check `app/db/models.py` for the actual required fields. The test fixture might need `Channel(...)` with whatever the model demands. Adjust `_seed` to satisfy NOT NULL columns in the actual model.

- [ ] **Step 3** — Run `uv run -m pytest tests/unit/test_set_post_text.py -x -v`. Expect 3 pass.

- [ ] **Step 4** — Commit.

```bash
git add app/channel/review/service.py tests/unit/test_set_post_text.py
git commit -m "feat(channel): add set_post_text verbatim setter"
```

---

### Task 2 — Webapi-owned Bot client

**Files:**
- Create: `app/webapi/services/publish_bot.py`
- Modify: `app/webapi/main.py`
- Modify: `app/webapi/deps.py`

- [ ] **Step 1** — `app/webapi/services/publish_bot.py`:

```python
"""Outgoing-only ``aiogram.Bot`` for the web admin process.

Creates an HTTP client to Telegram's Bot API for actions originated by the
admin UI (approve → publish, future: ban / unban). No dispatcher, no
``get_updates`` long-poll: only the in-process bot runs that loop. Multiple
processes can call the same outgoing endpoints — Telegram doesn't care.

Mirrors the moderator bot's defaults (``parse_mode='HTML'``) so message
formatting is consistent regardless of which process sent it.
"""
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger("webapi.publish_bot")


def build_publish_bot() -> Bot:
    """Construct the outgoing-only Bot. Caller is responsible for ``close()``."""
    return Bot(
        token=settings.telegram.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )


async def close_publish_bot(bot: Bot) -> None:
    with contextlib.suppress(Exception):
        await bot.session.close()
        logger.info("publish_bot_closed")
```

- [ ] **Step 2** — Wire in `_lifespan` of `app/webapi/main.py`:

```python
# Inside _lifespan, alongside telethon setup:
from app.webapi.services.publish_bot import build_publish_bot, close_publish_bot

publish_bot = build_publish_bot()
_app.state.publish_bot = publish_bot

# in finally block:
await close_publish_bot(publish_bot)
```

Also add a no-op default for tests (ASGITransport bypasses lifespan), similar to how `telethon_stats` is defaulted at end of `create_app`:

```python
# In create_app, after include_routers, before return:
app.state.publish_bot = None  # _lifespan replaces with real bot at startup
```

- [ ] **Step 3** — `get_publish_bot` dep in `app/webapi/deps.py`:

```python
from aiogram import Bot  # add to runtime imports

async def get_publish_bot(request: Request) -> Bot:
    """Return the process-wide publish Bot from app.state.

    Raises 503 if unavailable (e.g. test env that didn't override).
    """
    bot: Bot | None = getattr(request.app.state, "publish_bot", None)
    if bot is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="publish bot unavailable")
    return bot
```

- [ ] **Step 4** — Smoke check: `uv run -m pytest tests/webapi -x -q 2>&1 | tail -5`. Expect all-green; no test depends on `publish_bot` yet.

- [ ] **Step 5** — Commit.

```bash
git add app/webapi/services/publish_bot.py app/webapi/main.py app/webapi/deps.py
git commit -m "feat(webapi): add publish_bot lifecycle + dep"
```

---

### Task 3 — Schemas + endpoints

**Files:**
- Modify: `app/webapi/schemas.py`
- Modify: `app/webapi/routes/posts.py`

- [ ] **Step 1** — Schemas (append):

```python
class PostMutationResponse(BaseModel):
    """Outcome of a state-changing call against a post.

    ``status`` is the post's PostStatus *after* the mutation; ``message`` is the
    human-readable outcome from the service layer.
    """

    post_id: int
    status: str
    message: str
    published_msg_id: int | None = None


class PostTextEdit(BaseModel):
    text: str
```

- [ ] **Step 2** — Endpoints (append to `app/webapi/routes/posts.py`):

```python
from aiogram import Bot

from app.channel.publisher import publish_post as _publish_to_channel
from app.channel.review.service import approve_post, reject_post, set_post_text
from app.db.session import create_session_maker
from app.webapi.deps import get_publish_bot
from app.webapi.schemas import PostMutationResponse, PostTextEdit


@router.post("/{post_id}/approve", response_model=PostMutationResponse)
async def approve(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    async def _publish_fn(channel_id: int, gen_post: object) -> int | None:
        return await _publish_to_channel(bot, channel_id, gen_post)  # type: ignore[arg-type]

    msg, published_msg_id = await approve_post(
        post_id=post_id,
        channel_id=post.channel_id,
        publish_fn=_publish_fn,
        session_maker=create_session_maker(),
    )
    await session.refresh(post)
    return PostMutationResponse(
        post_id=post_id,
        status=post.status,
        message=msg,
        published_msg_id=published_msg_id,
    )


@router.post("/{post_id}/reject", response_model=PostMutationResponse)
async def reject(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    msg = await reject_post(post_id, create_session_maker())
    await session.refresh(post)
    return PostMutationResponse(post_id=post_id, status=post.status, message=msg)


@router.patch("/{post_id}/text", response_model=PostMutationResponse)
async def edit_text(
    post_id: int,
    payload: PostTextEdit,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    msg = await set_post_text(post_id, payload.text, create_session_maker())
    await session.refresh(post)
    return PostMutationResponse(post_id=post_id, status=post.status, message=msg)
```

Note on session reuse: the service functions use `session_maker()` to open their own sessions (with `with_for_update`). The route's request-scoped `session` parameter is used only to look up the post for the 404 check and to refresh after mutation. This avoids nested-transaction issues with `with_for_update`.

- [ ] **Step 3** — Tests `tests/webapi/test_post_mutations.py`:

```python
"""Tests for /api/posts/{id}/{approve,reject,text} mutations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from app.core.config import settings
from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession], monkeypatch):
    """Wire test session, stub publish_bot, dev-bypass auth."""
    from app.webapi.deps import get_publish_bot, get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    fake_bot = AsyncMock()
    fake_bot.session.close = AsyncMock()

    async def _override_publish_bot():
        return fake_bot

    # Service layer reaches for `create_session_maker()` directly — point it at the test maker.
    from app.db import session as session_mod
    monkeypatch.setattr(session_mod, "create_session_maker", lambda: db_session_maker)
    # Same import alias used inside posts.py
    from app.webapi.routes import posts as posts_route
    monkeypatch.setattr(posts_route, "create_session_maker", lambda: db_session_maker)
    # And in review service
    from app.channel.review import service as review_svc
    # service uses lazy `from app.db.session import create_session_maker` -- can't easily patch.
    # Instead, the route passes session_maker as parameter, which is already from create_session_maker().
    # The patch on posts_route.create_session_maker handles it.

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_publish_bot] = _override_publish_bot
    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make, fake_bot

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_publish_bot, None)


async def _seed_post(session: AsyncSession, *, status: PostStatus = PostStatus.DRAFT) -> int:
    ch = Channel(name="x", language="en", telegram_id=-100200)
    session.add(ch)
    await session.flush()
    post = ChannelPost(
        channel_id=ch.telegram_id,
        external_id="z" * 16,
        title="t",
        post_text="hello",
        status=status,
    )
    session.add(post)
    await session.commit()
    return post.id


async def test_edit_text_updates_post(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.patch(f"/api/posts/{post_id}/text", json={"text": "rewritten"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["post_id"] == post_id
    assert "updated" in body["message"].lower()

    async with db_session_maker() as s:
        from sqlalchemy import select
        post = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert post.post_text == "rewritten"


async def test_reject_marks_rejected(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.post(f"/api/posts/{post_id}/reject")
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        from sqlalchemy import select
        post = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert post.status == PostStatus.REJECTED


async def test_approve_calls_publisher(client_factory, db_session_maker, monkeypatch) -> None:
    make, _bot = client_factory
    # Stub the publisher used inside the route (avoids real Telegram call).
    from app.webapi.routes import posts as posts_route

    async def _fake_publish(*args, **kwargs):
        return 12345

    monkeypatch.setattr(posts_route, "_publish_to_channel", _fake_publish)

    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.post(f"/api/posts/{post_id}/approve")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["published_msg_id"] == 12345


async def test_404_when_missing(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.patch("/api/posts/99999/text", json={"text": "x"})
    assert resp.status_code == 404
```

The seed helper depends on actual `Channel` / `ChannelPost` constructor signatures — adjust the kwargs to satisfy the real model fields (look at `app/db/models.py` for what's required).

- [ ] **Step 4** — Run `uv run -m pytest tests/webapi/test_post_mutations.py -x -v`. Expect 4 pass.

- [ ] **Step 5** — Commit.

```bash
git add app/webapi/schemas.py app/webapi/routes/posts.py tests/webapi/test_post_mutations.py
git commit -m "feat(webapi): POST /posts/{id}/{approve,reject} + PATCH /text"
```

---

### Task 4 — Regen OpenAPI types + UI wiring

**Files:**
- Modify: `webui/src/lib/api/types.ts` (auto-gen)
- Modify: `webui/src/routes/posts/[id]/+page.svelte`

- [ ] **Step 1** — Regen types:

```bash
# from repo root, with .env present:
(uv run uvicorn app.webapi.main:app --host 127.0.0.1 --port 8787 > /tmp/sync.log 2>&1 &)
sleep 5
cd webui && pnpm run api:sync
pkill -f "uvicorn.*webapi"
```

- [ ] **Step 2** — Replace `webui/src/routes/posts/[id]/+page.svelte` script + buttons + body card:

```svelte
<script lang="ts">
  import { page } from '$app/state';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import * as Card from '$lib/components/ui/card/index.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import { apiFetch } from '$lib/api/client';
  import { toast } from 'svelte-sonner';
  import type { components } from '$lib/api/types';

  type PostDetail = components['schemas']['PostDetail'];
  type PostMutationResponse = components['schemas']['PostMutationResponse'];

  let post = $state<PostDetail | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let busy = $state<'approve' | 'reject' | 'save' | null>(null);
  let editing = $state(false);
  let draft = $state('');

  const postId = $derived(page.params.id);

  async function load(): Promise<void> {
    loading = true;
    const res = await apiFetch<PostDetail>(`/api/posts/${postId}`);
    if (res.error) {
      error = res.error.message;
      post = null;
    } else {
      post = res.data;
      draft = res.data.post_text ?? '';
      error = null;
    }
    loading = false;
  }

  $effect(() => {
    void load();
  });

  async function approve(): Promise<void> {
    if (busy) return;
    busy = 'approve';
    const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/approve`, { method: 'POST' });
    busy = null;
    if (res.error) toast.error(res.error.message);
    else {
      toast.success(res.data.message);
      await load();
    }
  }

  async function reject(): Promise<void> {
    if (busy) return;
    if (!confirm('Reject this post?')) return;
    busy = 'reject';
    const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/reject`, { method: 'POST' });
    busy = null;
    if (res.error) toast.error(res.error.message);
    else {
      toast.success(res.data.message);
      await load();
    }
  }

  async function save(): Promise<void> {
    if (busy) return;
    busy = 'save';
    const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/text`, {
      method: 'PATCH',
      body: JSON.stringify({ text: draft })
    });
    busy = null;
    if (res.error) toast.error(res.error.message);
    else {
      toast.success(res.data.message);
      editing = false;
      await load();
    }
  }

  function cancelEdit(): void {
    draft = post?.post_text ?? '';
    editing = false;
  }

  const canMutate = $derived(post && !['approved', 'rejected', 'skipped'].includes(post.status.toLowerCase()));
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
        <Button variant="default" size="sm" onclick={approve} disabled={!canMutate || busy !== null}>
          {busy === 'approve' ? 'Publishing…' : 'Approve'}
        </Button>
        <Button variant="outline" size="sm" onclick={reject} disabled={!canMutate || busy !== null}>
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
        <Button variant="outline" size="sm" onclick={() => (editing = !editing)} disabled={!canMutate || busy !== null}>
          {editing ? 'Cancel edit' : 'Edit'}
        </Button>
      </div>
    </header>

    <Card.Root>
      <Card.Header><Card.Title>Body</Card.Title></Card.Header>
      <Card.Content>
        {#if editing}
          <textarea
            bind:value={draft}
            class="min-h-[20rem] w-full resize-y rounded-md border border-zinc-200 p-3 font-mono text-sm leading-6 focus:border-zinc-400 focus:outline-none"
            disabled={busy === 'save'}
          ></textarea>
          <div class="mt-2 flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onclick={cancelEdit} disabled={busy === 'save'}>Cancel</Button>
            <Button size="sm" onclick={save} disabled={busy === 'save' || !draft.trim()}>
              {busy === 'save' ? 'Saving…' : 'Save'}
            </Button>
          </div>
        {:else}
          <pre class="whitespace-pre-wrap font-sans text-sm leading-6 text-zinc-800">{post.post_text}</pre>
        {/if}
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

Note: the project already includes `svelte-sonner`. Verify the toaster is mounted (likely in `+layout.svelte` or similar); if not, the `toast.success`/`toast.error` calls will silently no-op — check by grepping for `<Toaster />` in `webui/src/`. If absent, add `<Toaster />` to the auth-gated branch of `+layout.svelte`.

- [ ] **Step 3** — Run `cd webui && pnpm run check 2>&1 | tail -5`. Expect 0 errors.

- [ ] **Step 4** — Commit.

```bash
git add webui/src/lib/api/types.ts webui/src/routes/posts/\[id\]/+page.svelte webui/src/routes/+layout.svelte
git commit -m "feat(webui): wire approve/reject/edit on /posts/\[id\]"
```

---

### Task 5 — Final sweep + PR

- [ ] **Step 1** — `uv run ruff check app tests && uv run ruff format --check app tests && uv run ty check app tests` — clean (or no worse than baseline).
- [ ] **Step 2** — `uv run -m pytest -x` — all green.
- [ ] **Step 3** — `cd webui && pnpm run check` — 0 errors.
- [ ] **Step 4** — Push & open PR.

```bash
git push -u origin webui/phase-4b-posts-mutations
gh pr create --title "feat(webui): Phase 4b — posts approve / reject / edit mutations" --body ...
```

PR body should explain: webapi-owned Bot rationale, service-layer reuse, what's still stubbed (ban/unban → 4c, channel CRUD → 4d, settings → 4e).

---

## Out of Scope (later phases)

- **4c** — Channel CRUD: add/edit/delete channels, manage RSS sources, edit footer/schedule/limits
- **4d** — Chat moderation: ban/unban via global blacklist (UI on `/chats/[id]`)
- **4e** — `/settings` functional surface (TBD design)
