from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.application.services import report as report_services
from app.presentation.telegram.utils import other

groups_router = Router()


@groups_router.message(Command("report", prefix="!/"))
async def report_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        answer = await message.answer("Эту команду нужно использовать в ответ на сообщение.")
        other.sleep_and_delete(answer, 10)

    elif not message.reply_to_message.from_user:
        answer = await message.answer("Это не пользователь.")
        other.sleep_and_delete(answer, 10)

    else:
        if not message.from_user:
            await message.answer("Не удалось определить отправителя.")
            return
        reporter = message.from_user
        reported = message.reply_to_message.from_user
        reported_message = message.reply_to_message
        await report_services.report_to_moderators(bot, reporter, reported, reported_message)
        answer = await message.answer("Спасибо! Модераторы оповещены.👮")

    await message.delete()
