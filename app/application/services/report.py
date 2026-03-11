from aiogram import Bot, types

from app.core.config import settings
from app.core.markdown import md_to_entities


def _get_user_mention_md(user: types.User) -> str:
    """Return markdown mention for a user."""
    name = user.full_name or f"User {user.id}"
    return f"[{name}](tg://user?id={user.id})"


def _get_chat_link(message: types.Message) -> str:
    """Generate a link to the chat."""
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}"
    raw_id = str(chat.id)
    if raw_id.startswith("-100"):
        return f"https://t.me/c/{raw_id[4:]}"
    return f"https://t.me/c/{raw_id}"


def _get_message_link(message: types.Message) -> str:
    """Generate a direct link to a message."""
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}/{message.message_id}"
    raw_id = str(chat.id)
    if raw_id.startswith("-100"):
        return f"https://t.me/c/{raw_id[4:]}/{message.message_id}"
    return f"https://t.me/c/{raw_id}/{message.message_id}"


async def report_to_moderators(
    bot: Bot, reporter: types.User, reported: types.User, reported_message: types.Message
) -> None:
    chat_link = _get_chat_link(reported_message)
    chat_title = reported_message.chat.title or "Chat"
    msg_link = _get_message_link(reported_message)
    message_text = reported_message.text or ""

    text = (
        f"🚨 **От:** {_get_user_mention_md(reporter)}\n"
        f"🎯 **На:** {_get_user_mention_md(reported)}\n"
        f"💬 **Чат:** [{chat_title}]({chat_link})\n\n"
        f"📝 [Сообщение]({msg_link}):\n"
        f"{message_text}"
    )

    plain, entities = md_to_entities(text)
    await bot.send_message(
        chat_id=settings.admin.default_report_chat_id,
        text=plain,
        entities=entities,
        parse_mode=None,
    )
