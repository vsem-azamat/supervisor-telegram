"""!mute / !unmute commands."""

from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.core.logging import get_logger
from app.presentation.telegram.handlers.moderation._common import (
    is_user_check_error,
    reply_required_error,
)
from app.presentation.telegram.utils import other

logger = get_logger("handler.moderation.mute")
router = Router()


@router.message(Command("mute", prefix="!/"))
async def mute_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("замутить"))
        await message.delete()
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    mute_guide = (
        "Для мута пользователя используйте команду в формате:\n\n"
        "<code>!mute [время] [единица времени]</code>\n\n"
        "Примеры:\n<code>!mute 5m</code> - на 5 минут\n"
        "<code>!mute 1h</code> - на 1 час\n"
        "<code>!mute 1d</code> - на 1 день\n"
        "<code>!mute 1w</code> - на 1 неделю"
    )

    try:
        if not message.text:
            await message.answer("Команда не может быть пустой.")
            return
        mute_duration = other.calculate_mute_duration(message.text)
    except Exception:
        answer = await message.answer(f"Мне не удалось распознать время мута!\n\n{mute_guide}")
        await message.delete()
        other.sleep_and_delete(answer, 10)
        return

    read_only_permissions = types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
    )

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            permissions=read_only_permissions,
            until_date=mute_duration.until_date,
        )
        mention = other.get_user_mention(message.reply_to_message.from_user)
        text_mute = (
            f"{mention} в муте на {mute_duration.time} {mute_duration.unit}!\n\n"
            f"Дата размута: {mute_duration.formatted_until_date()}"
        )
        await message.reply_to_message.reply(text_mute)
        await message.delete()
    except Exception as err:
        await message.answer("Произошла ошибка. Попробуйте позже.")
        logger.error(
            "mute_failed",
            error=str(err),
            user_id=message.reply_to_message.from_user.id,
            chat_id=message.chat.id,
        )


@router.message(Command("unmute", prefix="!/"))
async def unmute_user(message: types.Message) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("размутить"))
        await message.delete()
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    default_permissions = message.chat.permissions
    if not default_permissions:
        await message.answer("Похоже, что я нахожусь не в чате или у меня нет прав администратора.")
        return

    try:
        await message.chat.restrict(
            user_id=message.reply_to_message.from_user.id,
            permissions=default_permissions,
            until_date=0,
        )
        mention = other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} размучен!")
    except Exception as err:
        await message.answer("Произошла ошибка. Попробуйте позже.")
        logger.error(
            "unmute_failed",
            error=str(err),
            user_id=message.reply_to_message.from_user.id,
            chat_id=message.chat.id,
        )
