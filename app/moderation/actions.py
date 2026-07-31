"""Carrying out a moderation action that a human confirmed.

This is what survives of the LLM moderation agent. The agent decided *whether*
to act; deciding is now a person's job, in the bot or through the control
plane, and only the doing is shared.

Two actions, because only two are ever proposed: everything else a moderator
does has its own command and acts immediately. A removal is the one thing worth
routing through a confirmation, so it is the one thing that needs an executor
separate from the handler that requested it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import ModerationAction
from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("moderation.actions")


class ActionNotExecutableError(Exception):
    """Raised when a stored action cannot be carried out.

    Loud on purpose: by the time this runs a human has pressed confirm and is
    entitled to believe the action happened.
    """


async def apply(
    action: ModerationAction,
    *,
    bot: Bot,
    db: AsyncSession,
    user_id: int,
    chat_id: int | None = None,
    revoke_messages: bool = False,
) -> None:
    """Carry out a confirmed action against one user."""
    match action:
        case ModerationAction.BAN:
            if chat_id is None:
                raise ActionNotExecutableError("ban needs a chat")
            await bot.ban_chat_member(chat_id, user_id)
            logger.info("action_ban", chat_id=chat_id, user_id=user_id)

        case ModerationAction.BLACKLIST:
            from app.moderation.blacklist import add_to_blacklist

            await add_to_blacklist(db, bot, user_id, revoke_messages=revoke_messages)
            logger.info("action_blacklist", user_id=user_id, revoke_messages=revoke_messages)


def parse(action: str) -> ModerationAction:
    """Turn a stored string back into the enum, refusing anything else.

    The database column is text, so this is the one place a value from outside
    the type system re-enters it.
    """
    try:
        return ModerationAction(action)
    except ValueError as err:
        raise ActionNotExecutableError(action) from err
