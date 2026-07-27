"""Join requests: turn blacklisted people away at the door.

Until now the blacklist was only enforced once someone was already inside — and
after the middleware fix, only at the moment they joined. A chat that requires
approval never reaches that moment, so the request itself has to be answered.

Nobody is approved here. Deciding who gets in is the operator's call; this only
removes the people they have already decided about.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, ChatJoinRequest, User
from app.db.models import Chat as DbChat
from app.db.models import User as DbUser
from app.presentation.telegram.handlers.events import join_requested
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

CHAT_ID = -1001234
USER_ID = 4242


def _request(query_id: str | None = None) -> ChatJoinRequest:
    user = User(id=USER_ID, is_bot=False, first_name="Applicant")
    return ChatJoinRequest(
        chat=Chat(id=CHAT_ID, type="supergroup", title="Managed"),
        from_user=user,
        user_chat_id=USER_ID,
        date=datetime.now(UTC),
        query_id=query_id,
    )


async def _seed_chat(session: AsyncSession) -> None:
    session.add(DbChat(id=CHAT_ID, title="Managed", resource_status=DbChat.STATUS_APPROVED))
    await session.commit()


async def _blacklist(session: AsyncSession) -> None:
    user = DbUser(id=USER_ID, username="spammer")
    user.blocked = True
    session.add(user)
    await session.commit()


@pytest.fixture
def bot() -> MagicMock:
    tg_bot = MagicMock()
    tg_bot.decline_chat_join_request = AsyncMock()
    tg_bot.approve_chat_join_request = AsyncMock()
    tg_bot.answer_chat_join_request_query = AsyncMock()
    return tg_bot


async def test_blacklisted_applicant_is_declined(session: AsyncSession, bot) -> None:
    await _seed_chat(session)
    await _blacklist(session)

    await join_requested(_request(), bot, session)

    bot.decline_chat_join_request.assert_awaited_once_with(chat_id=CHAT_ID, user_id=USER_ID)
    bot.approve_chat_join_request.assert_not_awaited()


async def test_ordinary_applicant_is_left_to_the_admins(session: AsyncSession, bot) -> None:
    """Approving is the operator's decision; the bot does not make it for them."""
    await _seed_chat(session)

    await join_requested(_request(), bot, session)

    bot.decline_chat_join_request.assert_not_awaited()
    bot.approve_chat_join_request.assert_not_awaited()


async def test_blacklisted_applicant_declined_through_the_query(session: AsyncSession, bot) -> None:
    """When acting as the chat's guard bot the answer goes back on the query."""
    await _seed_chat(session)
    await _blacklist(session)

    await join_requested(_request(query_id="q-1"), bot, session)

    bot.answer_chat_join_request_query.assert_awaited_once_with(chat_join_request_query_id="q-1", result="decline")
    bot.decline_chat_join_request.assert_not_awaited()


async def test_guarded_request_from_a_stranger_goes_to_the_admins(session: AsyncSession, bot) -> None:
    """A guard bot must answer, or the request hangs — 'queue' hands it over.

    There is no check to run yet, so passing it to the humans is the honest
    answer rather than approving on their behalf.
    """
    await _seed_chat(session)

    await join_requested(_request(query_id="q-2"), bot, session)

    bot.answer_chat_join_request_query.assert_awaited_once_with(chat_join_request_query_id="q-2", result="queue")


async def test_unknown_chat_is_left_alone(session: AsyncSession, bot) -> None:
    await _blacklist(session)

    await join_requested(_request(), bot, session)

    bot.decline_chat_join_request.assert_not_awaited()
    bot.answer_chat_join_request_query.assert_not_awaited()
