from aiogram import Router
from aiogram.filters import LEFT, MEMBER, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from app.core.logging import get_logger
from app.presentation.telegram.utils.filters import ChatTypeFilter

logger = get_logger("handler.events")
router = Router()


@router.chat_member(ChatTypeFilter(["group", "supergroup"]), ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_joined(_event: ChatMemberUpdated) -> None:
    logger.info("user_joined")


@router.chat_member(ChatTypeFilter(["group", "supergroup"]), ChatMemberUpdatedFilter(member_status_changed=LEFT))
async def user_left(_event: ChatMemberUpdated) -> None:
    logger.info("user_left")
