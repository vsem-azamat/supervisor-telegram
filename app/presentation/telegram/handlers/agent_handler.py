"""`/report` and `/spam` — a member asks admins to look at a message.

Mechanical: the bot forwards a summary with links back to the original. There
is no analysis step. There used to be one, reachable only from a tool on the
conversational assistant, and when that went the entry point went with it.
"""

from __future__ import annotations

from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import escape_html
from app.presentation.telegram.utils.other import get_chat_link, get_message_link, sleep_and_delete

logger = get_logger("handlers.agent")

agent_router = Router()

ESCALATION_LABELS = {
    "mute": "🔇 Замучен",
    "ban": "🚫 Забанен",
    "delete": "🗑 Удалено",
    "warn": "⚠️ Предупреждён",
    "blacklist": "☠️ Чёрный список",
    "ignore": "✅ Игнор",
}


@agent_router.message(Command("report", "spam"))
async def handle_report(
    message: types.Message,
    bot: Bot,
) -> None:
    """Handle /report and /spam — forward report to admin chat mechanically (no LLM)."""
    if not message.reply_to_message:
        answer = await message.answer(
            "Ответьте на сообщение, которое хотите отправить на проверку, командой /report или /spam."
        )
        await message.delete()
        sleep_and_delete(answer, 10)
        return

    target = message.reply_to_message
    if not target.from_user:
        await message.answer("🚫 Не удалось определить автора сообщения.")
        return

    # Build display name
    target_user = target.from_user
    display_name = target_user.first_name or ""
    if target_user.last_name:
        display_name += f" {target_user.last_name}"
    if not display_name:
        display_name = target_user.username or f"User {target_user.id}"

    reporter = message.from_user
    reporter_name = ""
    if reporter:
        reporter_name = reporter.first_name or ""
        if reporter.username:
            reporter_name = f"@{reporter.username}"

    command = (message.text or "").split()[0].lstrip("/").lower()
    event_label = "SPAM" if "spam" in command else "Report"

    # Truncate message text for the summary
    msg_text = target.text or target.caption or "[нет текста]"
    if len(msg_text) > 500:
        msg_text = msg_text[:500] + "..."

    chat_title = escape_html(message.chat.title) if message.chat.title else str(message.chat.id)
    chat_link = get_chat_link(message)
    message_link = get_message_link(target)
    username_part = f" (@{escape_html(target_user.username)})" if target_user.username else ""
    user_link = f'<a href="tg://user?id={target_user.id}">{escape_html(display_name)}</a>'

    summary = (
        f"📢 <b>{event_label}</b>\n\n"
        f'💬 Чат: <a href="{chat_link}">{chat_title}</a>\n'
        f"👤 Пользователь: {user_link}{username_part}\n"
        f"🆔 ID: <code>{target_user.id}</code>\n"
        f"📝 Отправил: {escape_html(reporter_name)}\n"
        f'🔗 <a href="{message_link}">Перейти к сообщению</a>\n\n'
        f"📄 Сообщение:\n<blockquote>{escape_html(msg_text)}</blockquote>"
    )

    # Send to admin report chat
    try:
        admin_chat_id = settings.admin.default_report_chat_id
        await bot.send_message(admin_chat_id, summary)
    except Exception as e:
        logger.error("Failed to forward report to admin", error=str(e))

    # Acknowledge in chat
    answer = await message.answer("📢 Жалоба отправлена администратору.")
    await message.delete()
    sleep_and_delete(answer, 10)
