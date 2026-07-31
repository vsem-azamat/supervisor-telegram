"""Shared helpers for the moderation handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import ModerationEventSource

if TYPE_CHECKING:
    from aiogram import types
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.enums import ModerationEventAction


def reply_required_error(action: str) -> str:
    """Standard error when a command should be a reply."""
    return f"Примените команду ответом на сообщение пользователя, которого нужно {action}. 🙏"


def is_user_check_error() -> str:
    """Standard error when target message does not contain a user."""
    return "🚫 Это не пользователь или что-то пошло не так."


async def record_reply_target(
    message: types.Message,
    db: AsyncSession,
    action: ModerationEventAction,
    *,
    detail: str | None = None,
) -> None:
    """Record an action taken against the author of the replied-to message.

    Every command here works the same way — an admin replies to somebody and
    names an action — so both the actor and the target are already on the
    message. Callers reach this only after the guards above have passed, and a
    missing user at that point means the command did nothing worth recording.
    """
    from app.moderation import audit

    target = message.reply_to_message.from_user if message.reply_to_message else None
    if target is None or message.from_user is None:
        return

    await audit.record(
        db,
        action=action,
        source=ModerationEventSource.COMMAND,
        actor_id=message.from_user.id,
        target_user_id=target.id,
        chat_id=message.chat.id,
        detail=detail,
    )
