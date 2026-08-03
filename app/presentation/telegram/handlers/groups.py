"""`/report` — the one thing an ordinary member can ask the bot to do."""

from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.moderation import report as report_services
from app.presentation.telegram.utils import other

groups_router = Router()


@groups_router.message(Command("report", prefix="!/"))
async def report_user(message: types.Message, bot: Bot) -> None:
    """Forward a message to the moderators.

    Both prefixes reach here. `/report` used to land in a different handler
    than `!report`, in another file, so the same complaint produced a different
    summary depending on which key the member happened to press — and `/spam`
    was a third name for it, one character away from the command that bans
    somebody out of every chat.
    """
    if not message.reply_to_message:
        answer = await message.answer("Ответьте этой командой на сообщение, которое нужно показать модераторам.")
        await message.delete()
        other.sleep_and_delete(answer, 10)
        return

    if not message.reply_to_message.from_user:
        answer = await message.answer("Это не сообщение пользователя.")
        await message.delete()
        other.sleep_and_delete(answer, 10)
        return

    if not message.from_user:
        return

    await report_services.report_to_moderators(
        bot,
        message.from_user,
        message.reply_to_message.from_user,
        message.reply_to_message,
    )
    answer = await message.answer("Спасибо! Жалоба отправлена модераторам.👮")
    await message.delete()
    other.sleep_and_delete(answer, 10)
