"""!ban / !unban commands."""

from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.core.logging import get_logger
from app.presentation.telegram.handlers.moderation._common import (
    is_user_check_error,
    reply_required_error,
)
from app.presentation.telegram.utils import other

logger = get_logger("handler.moderation.ban")
router = Router()


@router.message(Command("ban", prefix="!/"))
async def ban_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("забанить"))
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        mention = other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} забанен")
    except Exception as err:
        error_msg = await message.answer("Что-то пошло не так. Попробуйте позже.")
        logger.error(
            "ban_failed",
            error=str(err),
            user_id=message.reply_to_message.from_user.id,
            chat_id=message.chat.id,
        )
        other.sleep_and_delete(error_msg, 10)

    await message.delete()


@router.message(Command("unban", prefix="!/"))
async def unban_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("разбанить"))
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    try:
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        mention = other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} разбанен")
    except Exception as err:
        error_msg = await message.answer("Что-то пошло не так. Попробуйте позже.")
        logger.error(
            "unban_failed",
            error=str(err),
            user_id=message.reply_to_message.from_user.id,
            chat_id=message.chat.id,
        )
        other.sleep_and_delete(error_msg, 10)

    await message.delete()
