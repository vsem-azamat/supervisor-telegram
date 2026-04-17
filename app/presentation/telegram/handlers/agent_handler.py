"""Handlers for moderation reports (/report, /spam) and escalation callbacks.

/report and /spam are mechanical — they forward a summary to the admin chat.
LLM-based moderation analysis lives in the assistant bot (analyze_message tool).
Escalation callbacks (esc: prefix) remain here since escalation messages are
sent to admin via the moderator bot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Router, types
from aiogram.filters import Command

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import escape_html
from app.moderation.schemas import ActionType, AgentEvent, EventType
from app.presentation.telegram.utils.other import get_chat_link, get_message_link, sleep_and_delete

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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


@agent_router.callback_query(lambda c: c.data and c.data.startswith("esc:"))
async def handle_escalation_action(
    callback: types.CallbackQuery,
    bot: Bot,
    db: AsyncSession,
) -> None:
    """Handle admin's response to an escalation."""
    if not callback.data or not callback.from_user:
        await callback.answer("Ошибка")
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Неверный формат")
        return

    try:
        escalation_id = int(parts[1])
        chosen_action = parts[2]
    except (ValueError, IndexError):
        await callback.answer("Ошибка разбора")
        return

    if callback.from_user.id not in settings.admin.super_admins:
        await callback.answer("Только для супер-админов", show_alert=True)
        return

    # Resolve escalation (lazy import to avoid circular deps)
    from app.moderation.escalation import EscalationService

    escalation_svc = EscalationService(bot, db)
    escalation = await escalation_svc.resolve(
        escalation_id=escalation_id,
        admin_id=callback.from_user.id,
        action=chosen_action,
    )

    if not escalation:
        await callback.answer("Эскалация уже обработана или не найдена")
        return

    # Log admin override if agent's suggestion was different
    if escalation.decision_id and chosen_action != escalation.suggested_action:
        from app.moderation.memory import AgentMemory

        memory = AgentMemory(db)
        await memory.set_admin_override(escalation.decision_id, chosen_action)

    # Execute admin's chosen action directly (no AgentCore dependency needed)
    action_type = ActionType(chosen_action) if chosen_action in ActionType.__members__.values() else ActionType.IGNORE

    if action_type != ActionType.IGNORE:
        from app.moderation.agent import AgentCore

        event = AgentEvent(
            event_type=EventType.REPORT,
            chat_id=escalation.chat_id,
            chat_title=None,
            message_id=0,
            reporter_id=callback.from_user.id,
            target_user_id=escalation.target_user_id,
            target_username=None,
            target_display_name=str(escalation.target_user_id),
            target_message_text=escalation.message_text,
        )
        # Use AgentCore directly for action execution (no LLM call, just mechanical action)
        agent_core = AgentCore()
        await agent_core.execute_action(chosen_action, event, bot, db)

    # Update escalation message
    label = ESCALATION_LABELS.get(chosen_action, chosen_action)
    admin_name = callback.from_user.username or str(callback.from_user.id)

    if callback.message and isinstance(callback.message, types.Message):
        original_text = callback.message.text or ""
        await callback.message.edit_text(
            f"{escape_html(original_text)}\n\n✅ <b>Решение:</b> {label} (от @{escape_html(admin_name)})",
            reply_markup=None,
        )

    await callback.answer(f"Выполнено: {label}")
