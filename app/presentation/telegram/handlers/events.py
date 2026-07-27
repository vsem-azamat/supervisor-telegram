"""Membership changes in managed chats.

Only reached for approved chats: the approval gate runs on `dp.update` and stops
membership updates for anything still awaiting a decision, so nothing here needs
to re-check that.
"""

from aiogram import Bot, Router
from aiogram.filters import LEFT, MEMBER, ChatMemberUpdatedFilter
from aiogram.types import ChatJoinRequest, ChatMemberUpdated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Chat, User
from app.presentation.telegram.utils.filters import ChatTypeFilter
from app.presentation.telegram.utils.other import sleep_and_delete

logger = get_logger("handler.events")
router = Router()


@router.chat_member(ChatTypeFilter(["group", "supergroup"]), ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_joined(event: ChatMemberUpdated, bot: Bot, db: AsyncSession) -> None:
    """Greet a new member if the chat is configured to.

    A plain message rather than an ephemeral one. Bot API 10.2 says ephemeral
    delivery "is not guaranteed... especially if they are offline", which is
    acceptable for a reply to a command and useless for a greeting the new
    arrival may never see. It is cleaned up after `time_delete` seconds instead.
    """
    joined = event.new_chat_member.user
    logger.info("user_joined", chat_id=event.chat.id, user_id=joined.id)

    chat = await db.scalar(select(Chat).where(Chat.id == event.chat.id))
    if chat is None or not chat.is_welcome_enabled or not chat.welcome_message:
        return

    message = await bot.send_message(
        chat_id=event.chat.id,
        text=f"{joined.mention_html()}, {chat.welcome_message}",
    )

    if chat.time_delete:
        sleep_and_delete(message, chat.time_delete)


@router.chat_member(ChatTypeFilter(["group", "supergroup"]), ChatMemberUpdatedFilter(member_status_changed=LEFT))
async def user_left(event: ChatMemberUpdated) -> None:
    logger.info("user_left", chat_id=event.chat.id, user_id=event.new_chat_member.user.id)


@router.chat_join_request()
async def join_requested(event: ChatJoinRequest, bot: Bot, db: AsyncSession) -> None:
    """Turn away applicants who are already blacklisted.

    A chat that requires approval never produces the join event the blacklist
    middleware watches, so without this the ban only lands once an operator has
    let the person in.

    Nobody is approved here. Who gets in is the operator's decision; this only
    acts on people they have already decided about. When the bot is the chat's
    guard bot the answer has to travel back on the query — leaving it
    unanswered would hang the request — and `queue` is how it says "your call".
    """
    applicant = event.from_user
    chat = await db.scalar(select(Chat.id).where(Chat.id == event.chat.id))
    if chat is None:
        logger.info("join_request_ignored_unknown_chat", chat_id=event.chat.id)
        return

    blocked = await db.scalar(select(User.blocked).where(User.id == applicant.id))
    verdict = "decline" if blocked else "queue"
    logger.info("join_request", chat_id=event.chat.id, user_id=applicant.id, verdict=verdict)

    if event.query_id:
        await bot.answer_chat_join_request_query(chat_join_request_query_id=event.query_id, result=verdict)
        return

    if blocked:
        await bot.decline_chat_join_request(chat_id=event.chat.id, user_id=applicant.id)
