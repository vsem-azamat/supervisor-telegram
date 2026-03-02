"""Handlers for agent-powered moderation (/report, /spam, escalation callbacks)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import ActionType, AgentEvent, EventType
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.repositories import MessageRepository
from app.presentation.telegram.utils.other import sleep_and_delete

if TYPE_CHECKING:
    from app.agent.core import AgentCore

logger = get_logger("handlers.agent")

agent_router = Router()

ACTION_LABELS = {
    "mute": "🔇 Пользователь замучен",
    "ban": "🚫 Пользователь забанен",
    "delete": "🗑 Сообщение удалено",
    "warn": "⚠️ Предупреждение отправлено",
    "blacklist": "☠️ Пользователь в чёрном списке",
    "escalate": "⏳ Передано администратору",
    "ignore": "✅ Нарушений не обнаружено",
}

ESCALATION_LABELS = {
    "mute": "🔇 Замучен",
    "ban": "🚫 Забанен",
    "delete": "🗑 Удалено",
    "warn": "⚠️ Предупреждён",
    "blacklist": "☠️ Чёрный список",
    "ignore": "✅ Игнор",
}


def _get_event_type(command_text: str) -> EventType:
    if command_text and "spam" in command_text.lower():
        return EventType.SPAM
    return EventType.REPORT


async def _collect_context(
    message_repo: MessageRepository,
    target_user_id: int,
    chat_id: int,
) -> list[dict[str, str]]:
    """Collect recent messages from the target user for LLM context."""
    try:
        messages = await message_repo.get_user_messages(target_user_id, chat_id=chat_id)
        return [
            {"text": msg.content or "[no text]", "chat_id": str(msg.chat_id)}
            for msg in messages
            if msg.content
        ][:5]
    except Exception:
        return []


@agent_router.message(Command("report", "spam"))
async def handle_report(
    message: types.Message,
    bot: Bot,
    db: AsyncSession,
    agent_core: AgentCore,
    message_repo: MessageRepository,
) -> None:
    """Handle /report and /spam — trigger agent analysis."""
    if not settings.agent.enabled:
        answer = await message.answer("🤖 Агент отключён.")
        await message.delete()
        await sleep_and_delete(answer, 10)
        return

    if not message.reply_to_message:
        answer = await message.answer(
            "Ответьте на сообщение, которое хотите отправить на проверку, "
            "командой /report или /spam."
        )
        await message.delete()
        await sleep_and_delete(answer, 10)
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

    context_messages = await _collect_context(message_repo, target_user.id, message.chat.id)

    event = AgentEvent(
        event_type=_get_event_type(message.text or ""),
        chat_id=message.chat.id,
        chat_title=message.chat.title,
        message_id=target.message_id,
        reporter_id=message.from_user.id if message.from_user else 0,
        target_user_id=target_user.id,
        target_username=target_user.username,
        target_display_name=display_name,
        target_message_text=target.text or target.caption,
        context_messages=context_messages,
    )

    # Acknowledge
    status_msg = await message.answer("🤖 Анализирую сообщение...")
    await message.delete()

    # Run agent
    try:
        decision = await agent_core.process_report(event, bot, db)
    except Exception as e:
        logger.error("Agent processing failed", error=str(e))
        await status_msg.edit_text("❌ Ошибка обработки. Попробуйте позже.")
        return

    result_text = ACTION_LABELS.get(decision.action, decision.action)
    await status_msg.edit_text(f"{result_text}\n\n💬 {decision.reason}")


@agent_router.callback_query(lambda c: c.data and c.data.startswith("esc:"))
async def handle_escalation_action(
    callback: types.CallbackQuery,
    bot: Bot,
    db: AsyncSession,
    agent_core: AgentCore,
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
    from app.agent.escalation import EscalationService

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
        from app.agent.memory import AgentMemory

        memory = AgentMemory(db)
        await memory.set_admin_override(escalation.decision_id, chosen_action)

    # Execute admin's chosen action
    action_type = ActionType(chosen_action) if chosen_action in ActionType.__members__.values() else ActionType.IGNORE

    if action_type != ActionType.IGNORE:
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
        await agent_core.execute_action(chosen_action, event, bot, db)

    # Update escalation message
    label = ESCALATION_LABELS.get(chosen_action, chosen_action)
    admin_name = callback.from_user.username or str(callback.from_user.id)

    if callback.message and isinstance(callback.message, types.Message):
        original_text = callback.message.text or ""
        await callback.message.edit_text(
            f"{original_text}\n\n✅ <b>Решение:</b> {label} (от @{admin_name})",
            reply_markup=None,
        )

    await callback.answer(f"Выполнено: {label}")
