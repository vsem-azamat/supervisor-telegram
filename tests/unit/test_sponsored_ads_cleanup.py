import datetime
from typing import TYPE_CHECKING, cast

from app.core.time import utc_now
from app.db.models import Chat, Message
from app.sponsored_ads.cleanup import delete_ad_duplicates
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from aiogram import Bot

CHAT_A = -1001
CHAT_B = -1002
CHAT_C = -1003
UNMANAGED_CHAT = -1999


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


def _managed_chat(chat_id: int) -> Chat:
    return Chat(id=chat_id, title=f"Chat {chat_id}")


async def test_deletes_duplicates_across_chats(session: AsyncSession) -> None:
    spam = "Buy cheap iPhones @seller"
    session.add_all([_managed_chat(CHAT_A), _managed_chat(CHAT_B), _managed_chat(CHAT_C)])
    session.add_all(
        [
            _msg(CHAT_A, 11, 777, spam),
            _msg(CHAT_B, 22, 777, "  buy CHEAP   iphones @seller "),  # same after normalize
            _msg(CHAT_C, 33, 777, "totally different message"),
            _msg(CHAT_B, 99, 888, spam),  # different user — must not be touched
        ]
    )
    await session.commit()
    bot = _RecordingBot()

    result = await delete_ad_duplicates(
        cast("Bot", bot),
        session,
        user_id=777,
        origin_chat_id=CHAT_A,
        origin_message_id=11,
    )

    assert set(bot.deleted) == {(CHAT_A, 11), (CHAT_B, 22)}
    assert result.deleted == 2
    assert result.origin_text == spam


async def test_ignores_duplicates_in_unmanaged_chats(session: AsyncSession) -> None:
    spam = "Buy cheap iPhones @seller"
    session.add_all([_managed_chat(CHAT_A), _managed_chat(CHAT_B)])
    session.add_all(
        [
            _msg(CHAT_A, 11, 777, spam),
            _msg(CHAT_B, 22, 777, spam),
            _msg(UNMANAGED_CHAT, 99, 777, spam),
        ]
    )
    await session.commit()
    bot = _RecordingBot()

    result = await delete_ad_duplicates(
        cast("Bot", bot),
        session,
        user_id=777,
        origin_chat_id=CHAT_A,
        origin_message_id=11,
    )

    assert set(bot.deleted) == {(CHAT_A, 11), (CHAT_B, 22)}
    assert result.deleted == 2


async def test_ignores_messages_outside_window(session: AsyncSession) -> None:
    spam = "same spam text"
    old = utc_now() - datetime.timedelta(hours=48)
    session.add_all([_managed_chat(CHAT_A), _managed_chat(CHAT_B)])
    session.add_all(
        [
            _msg(CHAT_A, 11, 777, spam),
            _msg(CHAT_B, 22, 777, spam, ts=old),
        ]
    )
    await session.commit()
    bot = _RecordingBot()

    result = await delete_ad_duplicates(
        cast("Bot", bot),
        session,
        user_id=777,
        origin_chat_id=CHAT_A,
        origin_message_id=11,
    )

    assert set(bot.deleted) == {(CHAT_A, 11)}
    assert result.deleted == 1


async def test_origin_deleted_even_without_messages_row(session: AsyncSession) -> None:
    bot = _RecordingBot()
    result = await delete_ad_duplicates(
        cast("Bot", bot),
        session,
        user_id=777,
        origin_chat_id=CHAT_A,
        origin_message_id=11,
    )
    assert bot.deleted == [(CHAT_A, 11)]
    assert result.deleted == 1
    assert result.origin_text is None


async def test_delete_failure_is_skipped(session: AsyncSession) -> None:
    spam = "spam"
    session.add_all([_managed_chat(CHAT_A), _managed_chat(CHAT_B)])
    session.add_all(
        [
            _msg(CHAT_A, 11, 777, spam),
            _msg(CHAT_B, 22, 777, spam),
        ]
    )
    await session.commit()
    bot = _RecordingBot(fail_on={(CHAT_B, 22)})

    result = await delete_ad_duplicates(
        cast("Bot", bot),
        session,
        user_id=777,
        origin_chat_id=CHAT_A,
        origin_message_id=11,
    )
    assert result.deleted == 1  # CHAT_B/22 failed, counted out
