"""One tick of the member-count loop, over the Bot API.

It used to read through Telethon, which meant it read through an account whose
session lives on a developer's machine — so in production it asked nobody and
wrote nothing. The moderator bot is an administrator in every managed chat and
`getChatMemberCount` is a bot method; there was never a reason for the client
API here.

Counts are taken every tick because they are the point. Title and photo are
taken once a day, because they hardly ever change and each one is another call.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from app.chats.snapshots import METADATA_STALENESS_HOURS, snapshot_once
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _bot(*, counts: dict[int, int] | None = None, title: str = "Как в Telegram", photo: str | None = None):
    """A bot that answers about every chat unless told otherwise."""
    bot = AsyncMock()
    bot.get_chat_member_count = AsyncMock(side_effect=lambda chat_id: (counts or {}).get(chat_id, 42))

    async def _get_chat(chat_id: int):
        chat = MagicMock()
        chat.title = title
        chat.photo = MagicMock(big_file_id=photo) if photo else None
        return chat

    bot.get_chat = AsyncMock(side_effect=_get_chat)
    return bot


def _refused() -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message="chat not found")


async def _seed(session_maker, *chats: Chat) -> None:
    async with session_maker() as session:
        for chat in chats:
            session.add(chat)
        await session.commit()


async def _snapshots(session_maker) -> list[tuple[int, int]]:
    async with session_maker() as session:
        rows = (await session.execute(select(ChatMemberSnapshot).order_by(ChatMemberSnapshot.chat_id))).scalars().all()
    return [(row.chat_id, row.member_count) for row in rows]


async def _chat(session_maker, chat_id: int) -> Chat:
    async with session_maker() as session:
        return (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()


class TestCounting:
    async def test_a_row_per_chat(self, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
        await _seed(db_session_maker, Chat(id=-100, title="A"), Chat(id=-200, title="B"))

        written = await snapshot_once(session_maker=db_session_maker, bot=_bot(counts={-100: 50, -200: 80}))

        assert written == 2
        assert await _snapshots(db_session_maker) == [(-200, 80), (-100, 50)]

    async def test_a_chat_telegram_will_not_answer_about_is_skipped(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Not written as zero. Zero is a claim that the room is empty."""
        await _seed(db_session_maker, Chat(id=-100, title="A"))
        bot = _bot()
        bot.get_chat_member_count = AsyncMock(side_effect=_refused())

        written = await snapshot_once(session_maker=db_session_maker, bot=bot)

        assert written == 0
        assert await _snapshots(db_session_maker) == []

    async def test_one_silent_chat_does_not_stop_the_rest(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """On forty-five chats, one having removed the bot is an ordinary Tuesday."""
        await _seed(db_session_maker, Chat(id=-100, title="A"), Chat(id=-200, title="B"))
        bot = _bot()

        async def _count(chat_id: int) -> int:
            if chat_id == -100:
                raise _refused()
            return 80

        bot.get_chat_member_count = AsyncMock(side_effect=_count)

        await snapshot_once(session_maker=db_session_maker, bot=bot)

        assert await _snapshots(db_session_maker) == [(-200, 80)]

    async def test_counts_are_taken_even_for_a_freshly_synced_chat(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The staleness gate is about titles. The count is the reason for the tick."""
        chat = Chat(id=-100, title="A")
        chat.last_synced_at = utc_now()
        await _seed(db_session_maker, chat)

        await snapshot_once(session_maker=db_session_maker, bot=_bot(counts={-100: 50}))

        assert await _snapshots(db_session_maker) == [(-100, 50)]


class TestMetadata:
    async def test_a_stale_title_is_refreshed(self, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
        chat = Chat(id=-100, title="Старое имя")
        chat.last_synced_at = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
        await _seed(db_session_maker, chat)

        await snapshot_once(session_maker=db_session_maker, bot=_bot(title="Новое имя"))

        assert (await _chat(db_session_maker, -100)).title == "Новое имя"

    async def test_a_brand_new_chat_is_synced_immediately(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """No last_synced_at means never, which is older than any cutoff."""
        await _seed(db_session_maker, Chat(id=-100, title="Как записали"))

        await snapshot_once(session_maker=db_session_maker, bot=_bot(title="Как в Telegram"))

        refreshed = await _chat(db_session_maker, -100)
        assert refreshed.title == "Как в Telegram"
        assert refreshed.last_synced_at is not None

    async def test_a_recently_synced_chat_is_not_asked_again(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Titles change about never; the call is not free."""
        chat = Chat(id=-100, title="Как записали")
        chat.last_synced_at = utc_now()
        await _seed(db_session_maker, chat)
        bot = _bot(title="Как в Telegram")

        await snapshot_once(session_maker=db_session_maker, bot=bot)

        bot.get_chat.assert_not_awaited()
        assert (await _chat(db_session_maker, -100)).title == "Как записали"

    async def test_an_admin_edit_does_not_hold_off_a_sync(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The gate reads last_synced_at, never modified_at — otherwise editing
        the welcome text in the console would freeze the title."""
        chat = Chat(id=-100, title="Старое имя")
        chat.last_synced_at = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
        chat.modified_at = utc_now()
        await _seed(db_session_maker, chat)

        await snapshot_once(session_maker=db_session_maker, bot=_bot(title="Новое имя"))

        assert (await _chat(db_session_maker, -100)).title == "Новое имя"

    async def test_the_photo_is_cached(self, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
        await _seed(db_session_maker, Chat(id=-100, title="A"))

        await snapshot_once(session_maker=db_session_maker, bot=_bot(photo="file-123"))

        assert (await _chat(db_session_maker, -100)).photo_file_id == "file-123"

    async def test_a_chat_with_no_photo_keeps_the_one_we_had(
        self, db_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """A photo Telegram did not mention is not a photo that was removed."""
        chat = Chat(id=-100, title="A")
        chat.photo_file_id = "file-old"
        await _seed(db_session_maker, chat)

        await snapshot_once(session_maker=db_session_maker, bot=_bot(photo=None))

        assert (await _chat(db_session_maker, -100)).photo_file_id == "file-old"
