# Review Album UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a review post has 2+ images, show every image to the reviewer instead of just the first — by switching that case to a Telegram media group + a separate "pult" text message with the action buttons.

**Architecture:** New render helper in `telegram_io.py` picks one of three modes (`text` / `single` / `album`) based on `len(image_urls)`. A new rebuild helper does new-first-then-delete to swap album state without leaving dead callbacks. The existing `_refresh_after_change` seam in `agent.py` funnels into the new rebuild. DB gains a nullable `review_album_message_ids` JSON column.

**Tech Stack:** aiogram 3.x (`send_media_group`, `InputMediaPhoto`, `delete_messages`), SQLAlchemy 2.x async, Alembic, pytest + `FakeTelegramServer`.

**Spec:** `docs/superpowers/specs/2026-04-17-review-album-ui-design.md`

**Branch:** `feat/review-album-ui` (already checked out)

---

## File Structure

### Modified files

- `app/db/models.py` — add `review_album_message_ids: Mapped[list[int] | None]` column + `__init__` kwarg.
- `app/channel/review/telegram_io.py` — new `_render_review_message`, `_rebuild_review_message`; `send_for_review` persists new ids; `handle_regen` triggers rebuild; `handle_delete` cleans album.
- `app/channel/review/agent.py` — `_refresh_review_message` delegates to `_rebuild_review_message`.
- `tests/fake_telegram.py` — add `sendMediaGroup` and `deleteMessages` handlers with per-method recording of params.

### New files

- `alembic/versions/<auto>_add_review_album_message_ids.py` — migration.
- `tests/unit/test_review_render_modes.py` — unit tests for `_render_review_message`.
- `tests/unit/test_review_rebuild.py` — unit tests for `_rebuild_review_message`.
- `tests/unit/test_channel_post_album_ids.py` — ORM round-trip for the new field.
- `tests/e2e/test_review_album_e2e.py` — full flow via `FakeTelegramServer`.

---

## Task 1: DB column — `review_album_message_ids`

**Files:**
- Modify: `app/db/models.py:411-413` and `__init__` around `app/db/models.py:424-459`
- Create: `alembic/versions/<auto>_add_review_album_message_ids.py`
- Test: `tests/unit/test_channel_post_album_ids.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_channel_post_album_ids.py`:

```python
"""ORM round-trip for ChannelPost.review_album_message_ids."""

from __future__ import annotations

import pytest
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_review_album_message_ids_roundtrips_list_of_ints(session_maker):
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
            review_album_message_ids=[1001, 1002, 1003],
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        pid = p.id

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_album_message_ids == [1001, 1002, 1003]


async def test_review_album_message_ids_defaults_to_none(session_maker):
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="y",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        assert p.review_album_message_ids is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_channel_post_album_ids.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'review_album_message_ids'` or `AttributeError`.

- [ ] **Step 3: Add the column and __init__ kwarg**

In `app/db/models.py`, after the line `image_phashes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)` (currently line 413), add:

```python
    review_album_message_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
```

In `__init__` (currently around line 424-442), add parameter `review_album_message_ids: list[int] | None = None,` to the signature (group with the other `review_*` parameters), and `self.review_album_message_ids = review_album_message_ids` inside the body (group with the other assignments).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/unit/test_channel_post_album_ids.py -v`
Expected: PASS

- [ ] **Step 5: Generate the Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add review_album_message_ids to channel_posts"`

Expected: a new file under `alembic/versions/` named like `<hex>_add_review_album_message_ids_to_.py`.

- [ ] **Step 6: Verify migration contents**

Open the generated file. It should look structurally like:

```python
"""add review_album_message_ids to channel_posts

Revision ID: <hex>
Revises: 3e8dba58c88d
Create Date: ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<hex>'
down_revision: Union[str, None] = '3e8dba58c88d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'channel_posts',
        sa.Column('review_album_message_ids', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('channel_posts', 'review_album_message_ids')
```

If autogenerate added anything else (other tables/columns), **delete the extra ops** — the migration must only touch this one column. Confirm `down_revision` matches the latest existing migration (`3e8dba58c88d`).

- [ ] **Step 7: Commit**

```bash
git add app/db/models.py alembic/versions/*add_review_album_message_ids*.py tests/unit/test_channel_post_album_ids.py
git commit -m "feat(db): add review_album_message_ids column for album review mode"
```

---

## Task 2: FakeTelegramServer — `sendMediaGroup` and `deleteMessages`

**Files:**
- Modify: `tests/fake_telegram.py:68-213`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_fake_tg_album_endpoints.py`:

```python
"""Smoke test: FakeTelegramServer handles sendMediaGroup and deleteMessages."""

from __future__ import annotations

import json

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import InputMediaPhoto

from tests.fake_telegram import FakeTelegramServer

pytestmark = pytest.mark.asyncio


async def test_send_media_group_returns_distinct_message_ids():
    async with FakeTelegramServer() as server:
        bot = Bot(
            token="123:fake",
            session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
        )
        try:
            media = [
                InputMediaPhoto(media="https://example.com/a.jpg"),
                InputMediaPhoto(media="https://example.com/b.jpg"),
            ]
            messages = await bot.send_media_group(chat_id=-100, media=media)
        finally:
            await bot.session.close()

        assert len(messages) == 2
        assert messages[0].message_id != messages[1].message_id

        calls = server.get_calls("sendMediaGroup")
        assert len(calls) == 1
        media_param = calls[0].params.get("media")
        # aiogram serialises media as JSON string in multipart form
        parsed = json.loads(media_param) if isinstance(media_param, str) else media_param
        assert len(parsed) == 2


async def test_delete_messages_records_ids():
    async with FakeTelegramServer() as server:
        bot = Bot(
            token="123:fake",
            session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
        )
        try:
            ok = await bot.delete_messages(chat_id=-100, message_ids=[1001, 1002, 1003])
        finally:
            await bot.session.close()

        assert ok is True
        calls = server.get_calls("deleteMessages")
        assert len(calls) == 1
        ids_param = calls[0].params.get("message_ids")
        parsed = json.loads(ids_param) if isinstance(ids_param, str) else ids_param
        assert list(parsed) == [1001, 1002, 1003]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/e2e/test_fake_tg_album_endpoints.py -v`
Expected: FAIL. The generic fallback returns `{"ok": True, "result": True}` but `send_media_group` expects `result` to be a list of Message objects; aiogram will raise a validation error.

- [ ] **Step 3: Add handlers to FakeTelegramServer**

In `tests/fake_telegram.py`, after `_handle_deleteMessage` (currently around line 151-152) add two new methods:

```python
    def _handle_sendMediaGroup(self, params: dict[str, Any]) -> web.Response:
        """Return one minimal Message per item in the media list, with distinct ids."""
        import json as _json

        media_raw = params.get("media", "[]")
        try:
            media = _json.loads(media_raw) if isinstance(media_raw, str) else list(media_raw)
        except Exception:
            media = []
        chat_id = int(params.get("chat_id", 0))
        messages: list[dict[str, Any]] = []
        for _ in media:
            self._message_id_counter += 1
            messages.append(
                {
                    "message_id": self._message_id_counter,
                    "from": {"id": 5145935834, "is_bot": True, "first_name": "Test Bot"},
                    "chat": {"id": chat_id, "type": "supergroup", "title": "Test Chat"},
                    "date": 1700000000,
                    "photo": [
                        {
                            "file_id": f"photo-{self._message_id_counter}",
                            "file_unique_id": f"u-{self._message_id_counter}",
                            "width": 800,
                            "height": 600,
                            "file_size": 1024,
                        }
                    ],
                }
            )
        return web.json_response({"ok": True, "result": messages})

    def _handle_deleteMessages(self, params: dict[str, Any]) -> web.Response:
        """Bulk delete. Accept and record the list; return success."""
        return web.json_response({"ok": True, "result": True})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run -m pytest tests/e2e/test_fake_tg_album_endpoints.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/fake_telegram.py tests/e2e/test_fake_tg_album_endpoints.py
git commit -m "test: FakeTelegramServer handlers for sendMediaGroup and deleteMessages"
```

---

## Task 3: `_render_review_message` — the mode-aware renderer

**Files:**
- Modify: `app/channel/review/telegram_io.py:170-208` (replace `_send_review_message`)
- Test: `tests/unit/test_review_render_modes.py`

This task replaces the single-photo-or-text helper `_send_review_message` with a mode-aware `_render_review_message` that returns `(pult_message_id, album_message_ids | None)`. Call sites updated in later tasks.

- [ ] **Step 1: Write the failing test — text mode**

Create `tests/unit/test_review_render_modes.py`:

```python
"""Unit tests for _render_review_message: chooses the right mode based on image count."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.channel.review.telegram_io import _render_review_message

pytestmark = pytest.mark.asyncio


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="x")]])


async def test_render_text_mode_no_images():
    bot = SimpleNamespace()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=2001))
    bot.send_photo = AsyncMock()
    bot.send_media_group = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text="hello", image_urls=[], keyboard=_kb()
    )

    assert pult_id == 2001
    assert album_ids is None
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()


async def test_render_single_mode_one_image():
    bot = SimpleNamespace()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=2002))
    bot.send_media_group = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text="hello", image_urls=["https://x/a.jpg"], keyboard=_kb()
    )

    assert pult_id == 2002
    assert album_ids is None
    bot.send_photo.assert_awaited_once()
    # parse_mode must be None to preserve entities past the bot's default HTML mode
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs.get("parse_mode") is None
    bot.send_message.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()


async def test_render_album_mode_two_or_more_images():
    bot = SimpleNamespace()
    album_msgs = [SimpleNamespace(message_id=3001), SimpleNamespace(message_id=3002)]
    bot.send_media_group = AsyncMock(return_value=album_msgs)
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=3003))
    bot.send_photo = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot,
        chat_id=-100,
        post_text="hello",
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        keyboard=_kb(),
    )

    assert pult_id == 3003
    assert album_ids == [3001, 3002]
    bot.send_media_group.assert_awaited_once()
    # pult must reply to the first album photo so Telegram visually groups them
    pult_kwargs = bot.send_message.await_args.kwargs
    assert pult_kwargs.get("reply_to_message_id") == 3001
    assert pult_kwargs.get("parse_mode") is None
    bot.send_photo.assert_not_awaited()


async def test_render_single_mode_long_text_falls_back_to_text_message():
    """Existing behaviour: if caption > 1024 chars, image is dropped (text-only msg)."""
    bot = SimpleNamespace()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=4001))
    bot.send_photo = AsyncMock()
    bot.send_media_group = AsyncMock()

    long_text = "x" * 1100
    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text=long_text, image_urls=["https://x/a.jpg"], keyboard=_kb()
    )

    assert pult_id == 4001
    assert album_ids is None
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_review_render_modes.py -v`
Expected: FAIL with `ImportError: cannot import name '_render_review_message'`.

- [ ] **Step 3: Implement `_render_review_message`**

In `app/channel/review/telegram_io.py`, replace the existing `_send_review_message` function (currently lines ~173-208) with the new helper plus a thin back-compat wrapper. Put this in place of the existing `_send_review_message` body; keep `_edit_review_message` untouched below it.

```python
async def _render_review_message(
    bot: Bot,
    chat_id: int | str,
    post_text: str,
    image_urls: list[str] | None,
    keyboard: InlineKeyboardMarkup,
) -> tuple[int, list[int] | None]:
    """Send a review message in the right mode based on image count.

    Returns (pult_message_id, album_message_ids | None).
    - 0 images → text message (pult = that message; album = None)
    - 1 image, caption ≤ 1024 → photo with caption (pult = that photo; album = None)
    - 1 image, caption > 1024 → text-only fallback (image dropped; pult = text msg)
    - 2+ images → media group + separate pult text message as reply to first photo

    parse_mode=None is required everywhere to preserve entities past the bot's
    default HTML mode.
    """
    plain, entities = md_to_entities(post_text)
    urls = list(image_urls or [])

    if len(urls) >= 2:
        media = [URLInputFile(u) for u in urls[:10]]
        input_media = [InputMediaPhoto(media=p) for p in media]
        try:
            photos = await bot.send_media_group(chat_id=chat_id, media=input_media)
        except Exception:
            logger.exception("review_album_send_failed_fallback_to_single")
            photos = []

        if photos:
            pult_msg = await bot.send_message(
                chat_id=chat_id,
                text=plain,
                entities=entities,
                reply_markup=keyboard,
                reply_to_message_id=photos[0].message_id,
                disable_web_page_preview=True,
                parse_mode=None,
            )
            return pult_msg.message_id, [m.message_id for m in photos]

        # album failed — fall through to single-image path using the first url

    first_url = urls[0] if urls else None
    if first_url and len(plain) <= 1024:
        try:
            photo = URLInputFile(first_url)
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=plain,
                caption_entities=entities,
                reply_markup=keyboard,
                parse_mode=None,
            )
            return msg.message_id, None
        except Exception:
            logger.exception("review_photo_failed_fallback_to_text")

    msg = await bot.send_message(
        chat_id=chat_id,
        text=plain,
        entities=entities,
        reply_markup=keyboard,
        disable_web_page_preview=True,
        parse_mode=None,
    )
    return msg.message_id, None


async def _send_review_message(
    bot: Bot,
    chat_id: int | str,
    text: str,
    keyboard: InlineKeyboardMarkup,
    image_url: str | None = None,
) -> Message:
    """Back-compat wrapper that returns the pult Message only.

    Callers that still use this helper get single-message semantics (they cannot
    support album mode — they get the old behaviour). New code should use
    `_render_review_message` directly.
    """
    image_urls = [image_url] if image_url else []
    pult_id, _ = await _render_review_message(bot, chat_id, text, image_urls, keyboard)
    # Synthesise a minimal Message-like object; callers only use .message_id.
    return type("_StubMsg", (), {"message_id": pult_id})()  # type: ignore[return-value]
```

At the top of the file, add the needed import near `URLInputFile`:

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message, URLInputFile
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_review_render_modes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Check the whole existing test suite still passes**

Run: `uv run -m pytest tests/unit tests/e2e -x -q`
Expected: PASS. The `_send_review_message` back-compat wrapper keeps existing call sites working.

- [ ] **Step 6: Commit**

```bash
git add app/channel/review/telegram_io.py tests/unit/test_review_render_modes.py
git commit -m "feat(review): add _render_review_message with text/single/album modes"
```

---

## Task 4: Wire `send_for_review` to persist album ids

**Files:**
- Modify: `app/channel/review/telegram_io.py:251-311` (`send_for_review`)
- Test: `tests/unit/test_send_for_review_album.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_send_for_review_album.py`:

```python
"""send_for_review persists review_album_message_ids for 2+ image posts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.channel.generator import GeneratedPost
from app.channel.review.telegram_io import send_for_review
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class _Item:
    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url
        self.body = "b"
        self.source_url = url
        self.external_id = url
        self.summary = "s"


async def _bot_with_album(album_ids: list[int], pult_id: int):
    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(
        return_value=[SimpleNamespace(message_id=mid) for mid in album_ids]
    )
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=pult_id))
    bot.send_photo = AsyncMock()
    return bot


async def test_album_message_ids_persisted_when_two_images(session_maker):
    bot = await _bot_with_album(album_ids=[5001, 5002], pult_id=5003)
    post = GeneratedPost(
        text="Body\n\n——\n🔗 **Konnekt**",
        image_url="https://x/a.jpg",
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )
    items = [_Item("News", "https://src/1")]

    post_id = await send_for_review(
        bot,
        review_chat_id=-100,
        channel_id=-100,
        post=post,
        source_items=items,
        session_maker=session_maker,
    )
    assert post_id is not None

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_message_id == 5003
        assert row.review_album_message_ids == [5001, 5002]


async def test_album_message_ids_is_none_when_single_image(session_maker):
    bot = SimpleNamespace()
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=6001))
    bot.send_message = AsyncMock()
    bot.send_media_group = AsyncMock()
    post = GeneratedPost(
        text="Body\n\n——\n🔗 **Konnekt**",
        image_url="https://x/a.jpg",
        image_urls=["https://x/a.jpg"],
    )
    items = [_Item("News", "https://src/1")]

    post_id = await send_for_review(
        bot,
        review_chat_id=-100,
        channel_id=-100,
        post=post,
        source_items=items,
        session_maker=session_maker,
    )

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_message_id == 6001
        assert row.review_album_message_ids is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_send_for_review_album.py -v`
Expected: FAIL — `review_album_message_ids` is currently never set.

- [ ] **Step 3: Update `send_for_review`**

In `app/channel/review/telegram_io.py`, in `send_for_review` (around lines 251-311), replace the `_send_review_message` call and DB update block with a `_render_review_message` call that captures both ids:

```python
            msg_pult_id, msg_album_ids = await _render_review_message(
                bot, review_chat_id, post.text, post.image_urls or ([post.image_url] if post.image_url else []), keyboard
            )
            db_post.review_message_id = msg_pult_id
            db_post.review_album_message_ids = msg_album_ids
            await session.commit()
            logger.info(
                "review_sent",
                post_id=post_id,
                review_msg=msg_pult_id,
                album=len(msg_album_ids) if msg_album_ids else 0,
            )
            return post_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_send_for_review_album.py tests/e2e/test_channel_review.py -v`
Expected: PASS — both new tests and existing e2e review tests.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/telegram_io.py tests/unit/test_send_for_review_album.py
git commit -m "feat(review): persist album message ids in send_for_review"
```

---

## Task 5: `_rebuild_review_message` — new-first-then-delete

**Files:**
- Modify: `app/channel/review/telegram_io.py` (add new helper, near `_render_review_message`)
- Test: `tests/unit/test_review_rebuild.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_review_rebuild.py`:

```python
"""Unit tests for _rebuild_review_message: new-first-then-delete semantics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.channel.review.telegram_io import _rebuild_review_message
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="x")]])


async def _make_post(
    session_maker,
    *,
    review_message_id: int | None,
    album_ids: list[int] | None,
    image_urls: list[str] | None,
) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="Body",
            status=PostStatus.DRAFT,
            review_message_id=review_message_id,
            review_album_message_ids=album_ids,
            image_urls=image_urls,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_rebuild_album_to_album_commits_new_then_deletes_old(session_maker):
    """Happy path: post has 2 images, rebuild sends new album+pult, commits, then deletes old."""
    pid = await _make_post(
        session_maker,
        review_message_id=100,
        album_ids=[200, 201],
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    call_order: list[str] = []
    deleted_ids_capture: list[int] = []

    bot = SimpleNamespace()

    async def fake_send_media_group(**kwargs):
        call_order.append("send_media_group")
        return [SimpleNamespace(message_id=300), SimpleNamespace(message_id=301)]

    async def fake_send_message(**kwargs):
        call_order.append("send_message")
        return SimpleNamespace(message_id=302)

    async def fake_delete_messages(**kwargs):
        call_order.append("delete_messages")
        deleted_ids_capture.extend(kwargs["message_ids"])

    bot.send_media_group = fake_send_media_group
    bot.send_message = fake_send_message
    bot.send_photo = AsyncMock()
    bot.delete_messages = fake_delete_messages

    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    # New messages went out before the old ones were deleted.
    assert call_order == ["send_media_group", "send_message", "delete_messages"]
    # Original pult + album — order may vary, compare as a set.
    assert set(deleted_ids_capture) == {100, 200, 201}

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 302
        assert row.review_album_message_ids == [300, 301]


async def test_rebuild_single_to_album_deletes_old_single(session_maker):
    """Post had 1 image, reviewer added another → rebuild flips to album, deletes old single."""
    pid = await _make_post(
        session_maker,
        review_message_id=500,
        album_ids=None,
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    deleted_ids: list[int] = []
    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(
        return_value=[SimpleNamespace(message_id=600), SimpleNamespace(message_id=601)]
    )
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=602))
    bot.send_photo = AsyncMock()

    async def fake_delete_messages(**kwargs):
        deleted_ids.extend(kwargs["message_ids"])

    bot.delete_messages = fake_delete_messages

    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    assert deleted_ids == [500]  # only the old single pult

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 602
        assert row.review_album_message_ids == [600, 601]


async def test_rebuild_swallows_delete_errors(session_maker):
    """If delete_messages raises, DB was already committed — rebuild must not bubble the error."""
    pid = await _make_post(
        session_maker,
        review_message_id=700,
        album_ids=[701, 702],
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(
        return_value=[SimpleNamespace(message_id=800), SimpleNamespace(message_id=801)]
    )
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=802))
    bot.send_photo = AsyncMock()

    async def failing_delete(**kwargs):
        raise RuntimeError("too old")

    bot.delete_messages = failing_delete

    # Must not raise
    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 802
        assert row.review_album_message_ids == [800, 801]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_review_rebuild.py -v`
Expected: FAIL with `ImportError: cannot import name '_rebuild_review_message'`.

- [ ] **Step 3: Implement `_rebuild_review_message`**

In `app/channel/review/telegram_io.py`, add this function right after `_render_review_message`:

```python
async def _rebuild_review_message(
    bot: Bot,
    chat_id: int | str,
    post_id: int,
    session_maker: async_sessionmaker[AsyncSession],
    keyboard: InlineKeyboardMarkup,
) -> None:
    """Rebuild the review message for ``post_id``: new-first-then-delete.

    1. Fetch current post + old (pult_id, album_ids) from DB.
    2. Call ``_render_review_message`` with the post's current text/images.
    3. Commit the new ids to DB (callbacks on the new pult work immediately).
    4. Best-effort delete all old messages. Delete failures are logged, not raised.

    No-op when the post has no existing ``review_message_id``.
    """
    from sqlalchemy import select

    from app.db.models import ChannelPost

    async with session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = r.scalar_one_or_none()
        if post is None or not post.review_message_id:
            return
        old_ids: list[int] = [post.review_message_id]
        old_ids.extend(post.review_album_message_ids or [])
        post_text = post.post_text
        image_urls = list(post.image_urls or [])

    new_pult_id, new_album_ids = await _render_review_message(
        bot, chat_id, post_text, image_urls, keyboard
    )

    async with session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = r.scalar_one_or_none()
        if post is not None:
            post.review_message_id = new_pult_id
            post.review_album_message_ids = new_album_ids
            await session.commit()

    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=old_ids)
    except Exception:
        logger.warning("review_rebuild_delete_failed", post_id=post_id, old_ids=old_ids, exc_info=True)
```

If `async_sessionmaker` / `AsyncSession` aren't already imported in the runtime block (only `TYPE_CHECKING`), the import inside the function is fine.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_review_rebuild.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/telegram_io.py tests/unit/test_review_rebuild.py
git commit -m "feat(review): _rebuild_review_message with new-first-then-delete semantics"
```

---

## Task 6: Route agent image tools through `_rebuild_review_message`

**Files:**
- Modify: `app/channel/review/agent.py:460-605` (`_refresh_review_message` and `_refresh_after_change`)
- Test: `tests/unit/test_image_tool_rebuild_wiring.py`

The agent currently has its own `_refresh_review_message` helper that does a per-single-image delete-and-resend. Replace it with a call to the new `_rebuild_review_message` from `telegram_io.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_image_tool_rebuild_wiring.py`:

```python
"""The agent's _refresh_review_message helper delegates to telegram_io._rebuild_review_message.

We don't test via the PydanticAI toolset registry (internals change too often);
we test the seam by reaching into the `create_review_agent` factory's closure —
it binds `_refresh_after_change` as a nested function. That's brittle too, so
instead we verify the agent module imports and calls `_rebuild_review_message`
from telegram_io, and route through the public `review_agent_turn` in a later
e2e test (Task 9 covers the end-to-end behaviour).
"""

from __future__ import annotations

import pytest


def test_agent_module_uses_telegram_io_rebuild():
    """Lexical check: agent.py imports and references _rebuild_review_message."""
    import app.channel.review.agent as agent_mod
    import inspect

    src = inspect.getsource(agent_mod)
    assert "_rebuild_review_message" in src, (
        "agent.py should route image-tool refresh through telegram_io._rebuild_review_message"
    )
    # The old per-message delete-and-single-send path must be gone.
    assert "bot.delete_message(chat_id=review_chat_id, message_id=post.review_message_id)" not in src, (
        "agent.py should no longer open-code single-message delete-and-resend; "
        "that logic lives in telegram_io._rebuild_review_message now."
    )
```

This is a lightweight regression-guard test. Task 9 (e2e) covers the full runtime behaviour end-to-end.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_image_tool_rebuild_wiring.py -v`
Expected: FAIL — `_rebuild_review_message` is never called from agent.py today.

- [ ] **Step 3: Replace `_refresh_review_message` in agent.py**

In `app/channel/review/agent.py`, replace the whole `_refresh_review_message` function (currently lines ~460-517) with a thin delegator, and update `_refresh_after_change` (currently lines ~594-604) to call it.

```python
    async def _refresh_review_message(ctx: RunContext[ReviewAgentDeps], post: Any) -> str | None:
        """Delegate to the telegram_io rebuild helper.

        The ``post`` argument is unused — the helper re-fetches from DB to avoid
        stale state. Kept for API compatibility with earlier callers.
        """
        del post
        from app.channel.review.telegram_io import _rebuild_review_message, build_review_keyboard

        try:
            # Re-fetch to build a fresh keyboard (source items may have changed).
            from sqlalchemy import select as _select
            from app.db.models import ChannelPost

            async with ctx.deps.session_maker() as session:
                r = await session.execute(_select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
                fresh_post = r.scalar_one_or_none()

            if fresh_post is None:
                return "Warning: post not found during refresh."

            from app.channel.review.service import extract_source_btn_data

            keyboard = build_review_keyboard(
                ctx.deps.post_id,
                source_items=extract_source_btn_data(fresh_post),
                channel_name=ctx.deps.channel_name,
                channel_username=ctx.deps.channel_username,
            )
            await _rebuild_review_message(
                ctx.deps.bot,
                ctx.deps.review_chat_id,
                ctx.deps.post_id,
                ctx.deps.session_maker,
                keyboard,
            )

            # Register the new pult in the reply chain (post.review_message_id now updated)
            async with ctx.deps.session_maker() as session:
                r = await session.execute(_select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
                refreshed = r.scalar_one_or_none()
            if refreshed and refreshed.review_message_id:
                register_message(refreshed.review_message_id, ctx.deps.post_id)
                await persist_message_to_db(
                    ctx.deps.session_maker, ctx.deps.post_id, refreshed.review_message_id
                )

            return None
        except Exception:
            logger.exception("review_message_refresh_failed", post_id=ctx.deps.post_id)
            return "Warning: review message could not be refreshed."

    async def _refresh_after_change(ctx: RunContext[ReviewAgentDeps]) -> None:
        """Re-fetch the post and rebuild the review message."""
        await _refresh_review_message(ctx, None)
```

Drop the no-longer-needed imports at the top of the old `_refresh_review_message` (`_send_review_message`, `extract_source_btn_data`) — the delegator fetches them lazily.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_image_tool_rebuild_wiring.py tests/unit/test_review_agent.py tests/e2e/test_channel_review.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/agent.py tests/unit/test_image_tool_rebuild_wiring.py
git commit -m "refactor(review): route image tool refresh through _rebuild_review_message"
```

---

## Task 7: `handle_regen` triggers a full rebuild

**Files:**
- Modify: `app/channel/review/telegram_io.py:411-457` (`handle_regen`)
- Test: `tests/unit/test_handle_regen_rebuild.py`

Regen may change both text **and** images (image pipeline runs again inside `regen_post_text`). The existing `handle_regen` only edits the pult caption — broken for album. Route it through `_rebuild_review_message`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_handle_regen_rebuild.py`:

```python
"""handle_regen rebuilds the review message when images changed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.review.telegram_io import handle_regen
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="Body",
            status=PostStatus.DRAFT,
            image_urls=["https://x/a.jpg"],
            review_message_id=1000,
            review_album_message_ids=None,
            source_items=[{"title": "t", "url": "https://src", "source_url": "https://src", "external_id": "x"}],
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_handle_regen_always_calls_rebuild(session_maker):
    pid = await _make_post(session_maker)

    # Stub out regen_post_text to return an "updated" post (same DB row).
    async def fake_regen_post_text(post_id, api_key, model, language, session_maker, *, footer):
        async with session_maker() as s:
            r = await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = r.scalar_one_or_none()
            if post:
                post.image_urls = ["https://x/a.jpg", "https://x/new.jpg"]
                await s.commit()
                await s.refresh(post)
            return "Post regenerated.", post

    with (
        patch("app.channel.review.telegram_io.regen_post_text", side_effect=fake_regen_post_text),
        patch("app.channel.review.telegram_io._rebuild_review_message", new=AsyncMock()) as rebuild,
    ):
        bot = SimpleNamespace()
        status = await handle_regen(
            bot,
            post_id=pid,
            api_key="k",
            model="m",
            language="Russian",
            review_chat_id=-100,
            session_maker=session_maker,
            footer="— Konnekt",
        )
        assert "regenerated" in status.lower()
        rebuild.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/unit/test_handle_regen_rebuild.py -v`
Expected: FAIL — `handle_regen` currently calls `_edit_review_message`, not `_rebuild_review_message`.

- [ ] **Step 3: Rewrite `handle_regen`**

In `app/channel/review/telegram_io.py`, replace the body of `handle_regen` (currently lines ~411-456) with:

```python
async def handle_regen(
    bot: Bot,
    post_id: int,
    api_key: str,
    model: str,
    language: str,
    review_chat_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    footer: str = "",
    channel_name: str = "",
    channel_username: str | None = None,
) -> str:
    """Regenerate a post from its original sources. Always rebuilds the review message."""
    status_msg, updated_post = await regen_post_text(
        post_id=post_id,
        api_key=api_key,
        model=model,
        language=language,
        session_maker=session_maker,
        footer=footer,
    )

    if updated_post and updated_post.review_message_id:
        source_btn_data = extract_source_btn_data(updated_post)
        keyboard = build_review_keyboard(
            post_id,
            source_items=source_btn_data,
            channel_name=channel_name,
            channel_username=channel_username,
        )
        try:
            await _rebuild_review_message(bot, review_chat_id, post_id, session_maker, keyboard)
        except Exception:
            logger.exception("review_regen_rebuild_error")

    return status_msg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_handle_regen_rebuild.py tests/e2e/test_channel_review.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/telegram_io.py tests/unit/test_handle_regen_rebuild.py
git commit -m "feat(review): handle_regen triggers full rebuild (text + images)"
```

---

## Task 8: `handle_delete` cleans album messages

**Files:**
- Modify: `app/channel/review/telegram_io.py:339-356` (`handle_delete`)
- Test: `tests/unit/test_handle_delete_album.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_handle_delete_album.py`:

```python
"""handle_delete deletes pult AND album photos when present."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.channel.review.telegram_io import handle_delete
from app.core.enums import PostStatus
from app.db.models import ChannelPost

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker, *, review_mid: int, album_ids: list[int] | None) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
            review_message_id=review_mid,
            review_album_message_ids=album_ids,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_delete_removes_album_plus_pult(session_maker):
    pid = await _make_post(session_maker, review_mid=100, album_ids=[101, 102, 103])
    deleted: list[int] = []

    bot = SimpleNamespace()

    async def fake_delete_messages(**kwargs):
        deleted.extend(kwargs["message_ids"])

    async def fake_delete_message(**kwargs):
        deleted.append(kwargs["message_id"])

    bot.delete_messages = fake_delete_messages
    bot.delete_message = fake_delete_message

    await handle_delete(bot, pid, -100, 100, session_maker)
    assert set(deleted) == {100, 101, 102, 103}


async def test_delete_with_no_album_still_deletes_pult(session_maker):
    pid = await _make_post(session_maker, review_mid=200, album_ids=None)
    deleted: list[int] = []

    bot = SimpleNamespace()

    async def fake_delete_message(**kwargs):
        deleted.append(kwargs["message_id"])

    async def fake_delete_messages(**kwargs):
        deleted.extend(kwargs["message_ids"])

    bot.delete_message = fake_delete_message
    bot.delete_messages = fake_delete_messages

    await handle_delete(bot, pid, -100, 200, session_maker)
    assert deleted == [200]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run -m pytest tests/unit/test_handle_delete_album.py -v`
Expected: FAIL — first test fails because only pult is deleted today.

- [ ] **Step 3: Update `handle_delete`**

In `app/channel/review/telegram_io.py`, replace `handle_delete` (currently lines ~339-356) with:

```python
async def handle_delete(
    bot: Bot,
    post_id: int,
    review_chat_id: int | str,
    review_message_id: int | None,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Skip a post (soft-delete) and remove the review messages from chat."""
    from sqlalchemy import select

    from app.db.models import ChannelPost

    album_ids: list[int] = []
    async with session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = r.scalar_one_or_none()
        if post and post.review_album_message_ids:
            album_ids = list(post.review_album_message_ids)

    status_msg, skipped_post = await delete_post(post_id, session_maker)

    if skipped_post:
        # Delete album photos in bulk (best-effort).
        if album_ids:
            try:
                await bot.delete_messages(chat_id=review_chat_id, message_ids=album_ids)
            except Exception:
                logger.warning("review_album_delete_failed", post_id=post_id, exc_info=True)
        # Delete pult.
        if review_message_id:
            try:
                await bot.delete_message(chat_id=review_chat_id, message_id=review_message_id)
            except Exception:
                logger.warning("review_message_delete_failed", post_id=post_id, exc_info=True)

    return status_msg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run -m pytest tests/unit/test_handle_delete_album.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/channel/review/telegram_io.py tests/unit/test_handle_delete_album.py
git commit -m "feat(review): handle_delete removes album photos too"
```

---

## Task 9: End-to-end smoke test — full album review flow

**Files:**
- Create: `tests/e2e/test_review_album_e2e.py`

- [ ] **Step 1: Write the failing test**

Create `tests/e2e/test_review_album_e2e.py`:

```python
"""Full review-flow smoke test: album send → approve chain via FakeTelegramServer."""

from __future__ import annotations

import json

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from app.channel.generator import GeneratedPost
from app.channel.review.telegram_io import send_for_review, handle_delete
from app.db.models import ChannelPost
from sqlalchemy import select

from tests.fake_telegram import FakeTelegramServer

pytestmark = pytest.mark.asyncio


class _Item:
    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url
        self.body = "b"
        self.source_url = url
        self.external_id = url
        self.summary = "s"


async def _make_bot(server: FakeTelegramServer) -> Bot:
    return Bot(
        token="123:fake",
        session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
    )


async def test_send_album_for_review_produces_media_group_plus_pult(session_maker, fake_tg):
    bot = await _make_bot(fake_tg)
    try:
        post = GeneratedPost(
            text="Body text\n\n——\n🔗 **Konnekt**",
            image_url="https://x/a.jpg",
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        )
        post_id = await send_for_review(
            bot,
            review_chat_id=-100,
            channel_id=-100,
            post=post,
            source_items=[_Item("News", "https://src/1")],
            session_maker=session_maker,
        )
        assert post_id is not None
    finally:
        await bot.session.close()

    mg_calls = fake_tg.get_calls("sendMediaGroup")
    msg_calls = fake_tg.get_calls("sendMessage")
    assert len(mg_calls) == 1
    assert len(msg_calls) == 1

    mg_params = mg_calls[0].params
    media_raw = mg_params.get("media", "[]")
    media = json.loads(media_raw) if isinstance(media_raw, str) else media_raw
    assert len(media) == 2

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_album_message_ids and len(row.review_album_message_ids) == 2
        assert row.review_message_id


async def test_delete_album_post_issues_bulk_delete(session_maker, fake_tg):
    bot = await _make_bot(fake_tg)
    try:
        post = GeneratedPost(
            text="Body\n\n——\n🔗 **Konnekt**",
            image_url="https://x/a.jpg",
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        )
        post_id = await send_for_review(
            bot,
            review_chat_id=-100,
            channel_id=-100,
            post=post,
            source_items=[_Item("News", "https://src/1")],
            session_maker=session_maker,
        )
        assert post_id is not None

        async with session_maker() as s:
            row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            pult = row.review_message_id

        fake_tg.reset()  # only observe the delete-path calls below

        await handle_delete(bot, post_id, -100, pult, session_maker)
    finally:
        await bot.session.close()

    # One bulk delete for the 2 album photos, plus one single delete for the pult.
    assert len(fake_tg.get_calls("deleteMessages")) == 1
    assert len(fake_tg.get_calls("deleteMessage")) == 1
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run -m pytest tests/e2e/test_review_album_e2e.py -v`
Expected: PASS (2 tests). All wiring from Tasks 1–8 is in place.

- [ ] **Step 3: Run the full test suite as a regression check**

Run: `uv run -m pytest -q`
Expected: all previously-passing tests still pass; new tests added by this plan pass.

- [ ] **Step 4: Lint + typecheck**

```bash
uv run ruff check app tests && uv run ruff format --check app tests && uv run ty check app tests
```
Expected: no violations.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_review_album_e2e.py
git commit -m "test(e2e): album review flow via FakeTelegramServer"
```

---

## Final Step: Open the PR

- [ ] **Push the branch and open a PR**

```bash
git push -u origin feat/review-album-ui
gh pr create --title "feat(review): show full album during review (Sprint 1.5)" --body "$(cat <<'EOF'
## Summary
- Review flow now sends `send_media_group` + a separate pult text message for posts with 2+ images, so reviewers see every image the agent composed.
- Image tool edits (`use_candidate`, `remove_image`, `reorder_images`, etc.) and `/regen` rebuild the review using new-first-then-delete to avoid dead-callback windows.
- New nullable `ChannelPost.review_album_message_ids` JSON column tracks the album photo ids alongside the existing `review_message_id` (the pult).

## Test plan
- [ ] `uv run -m pytest tests/unit/test_channel_post_album_ids.py tests/unit/test_review_render_modes.py tests/unit/test_review_rebuild.py tests/unit/test_send_for_review_album.py tests/unit/test_handle_regen_rebuild.py tests/unit/test_handle_delete_album.py -v`
- [ ] `uv run -m pytest tests/e2e/test_review_album_e2e.py tests/e2e/test_fake_tg_album_endpoints.py -v`
- [ ] `uv run -m pytest -q` — full regression
- [ ] Manual: publish a multi-image draft in the Konnekt Review group, verify both the album and the button pult render; use `use_candidate` / `remove_image` / `regen` and watch the review rebuild itself cleanly.

Design spec: `docs/superpowers/specs/2026-04-17-review-album-ui-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
