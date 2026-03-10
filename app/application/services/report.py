from aiogram import Bot, types

from app.core.config import settings
from app.core.text import escape_html
from app.presentation.telegram.utils import other


async def report_to_moderators(
    bot: Bot, reporter: types.User, reported: types.User, reported_message: types.Message
) -> None:
    chat_mention = other.get_chat_mention(reported_message)
    reported_message_metion = other.get_message_mention(reported_message)

    message_text = escape_html(reported_message.text) if reported_message.text else ""
    text = (
        f"🚨 <b>От:</b> {other.get_user_mention(reporter)}\n"
        f"🎯 <b>На:</b> {other.get_user_mention(reported)}\n"
        f"💬 <b>Чат:</b> {chat_mention}\n\n"
        f"📝 {reported_message_metion}:\n"
        f"{message_text}"
    )
    await bot.send_message(chat_id=settings.admin.default_report_chat_id, text=text)
