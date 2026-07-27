"""Moderation tools that change something.

Two tiers, split by how bad the mistake is.

A mute is bounded and self-reversing, an unban restores access, a welcome
message is text — those run on the call and are recorded. A ban removes a
person, and a blacklist entry removes them from every chat at once; those are
proposed and wait for a super admin to press confirm in the moderator bot.

So a leaked token can queue noise into an admin's private chat, which is loud
and harmless, but it cannot remove anybody.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.mcp.deps import ToolError, approved_chat_id, clamp, initiator_id, moderator_bot, session_maker

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger("mcp.tools.moderate")

MAX_MUTE_MINUTES = 43200


def register_moderation_tools(mcp: FastMCP[None]) -> None:
    """Register the write and confirm tiers."""

    @mcp.tool
    async def mute_user(chat_id: int, user_id: int, minutes: int = 5) -> dict[str, Any]:
        """Silence a user in one chat for a while.

        chat_id must be an approved chat — the bot does not act publicly in
        one still awaiting approval. minutes is clamped to 1..43200 (30 days),
        the longest restriction Telegram accepts. Reversible with unmute_user,
        so this runs immediately rather than asking for confirmation.
        """
        from aiogram.types import ChatPermissions

        try:
            minutes = clamp(minutes, 1, MAX_MUTE_MINUTES)
            bot = moderator_bot()
            async with session_maker()() as session:
                await approved_chat_id(session, chat_id)

            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes),
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    # Added in Bot API 10.0; muting without it leaves the user
                    # able to keep reacting to messages.
                    can_react_to_messages=False,
                ),
            )
        except ToolError as err:
            return err.payload()

        logger.info("mcp_mute", chat_id=chat_id, user_id=user_id, minutes=minutes)
        return {"status": "muted", "chat_id": chat_id, "user_id": user_id, "minutes": minutes}

    @mcp.tool
    async def unmute_user(chat_id: int, user_id: int) -> dict[str, Any]:
        """Restore a muted user's ability to post in one chat."""
        from aiogram.types import ChatPermissions

        try:
            bot = moderator_bot()
            async with session_maker()() as session:
                await approved_chat_id(session, chat_id)

            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_react_to_messages=True,
                ),
            )
        except ToolError as err:
            return err.payload()

        logger.info("mcp_unmute", chat_id=chat_id, user_id=user_id)
        return {"status": "unmuted", "chat_id": chat_id, "user_id": user_id}

    @mcp.tool
    async def unban_user(chat_id: int, user_id: int) -> dict[str, Any]:
        """Let a banned user back into one chat.

        Restores access rather than removing it, so it needs no confirmation.
        """
        try:
            bot = moderator_bot()
            async with session_maker()() as session:
                await approved_chat_id(session, chat_id)

            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        except ToolError as err:
            return err.payload()

        logger.info("mcp_unban", chat_id=chat_id, user_id=user_id)
        return {"status": "unbanned", "chat_id": chat_id, "user_id": user_id}

    @mcp.tool
    async def unblacklist_user(user_id: int) -> dict[str, Any]:
        """Remove a user from the global blacklist.

        The blacklist spans every managed chat; this lifts it everywhere.
        """
        from app.core.exceptions import UserNotFoundException
        from app.moderation.blacklist import remove_from_blacklist

        try:
            bot = moderator_bot()
            async with session_maker()() as session:
                try:
                    await remove_from_blacklist(session, bot, user_id)
                except UserNotFoundException:
                    return {"error": "unknown_user", "user_id": user_id}
        except ToolError as err:
            return err.payload()

        logger.info("mcp_unblacklist", user_id=user_id)
        return {"status": "unblacklisted", "user_id": user_id}

    @mcp.tool
    async def set_welcome(chat_id: int, message: str = "", enabled: bool = True) -> dict[str, Any]:
        """Set a chat's welcome text and whether it is enabled.

        The greeting is posted when someone joins and removed again after the
        chat's configured lifetime. Passing an empty message leaves the existing
        text alone and only changes the toggle.
        """
        from sqlalchemy import select

        from app.db.models import Chat

        try:
            async with session_maker()() as session:
                await approved_chat_id(session, chat_id)
                chat = await session.scalar(select(Chat).where(Chat.id == chat_id))
                if chat is None:  # pragma: no cover - approved_chat_id already refused
                    return {"error": "unknown_chat"}
                if message:
                    chat.welcome_message = message
                chat.is_welcome_enabled = enabled
                await session.commit()
        except ToolError as err:
            return err.payload()

        logger.info("mcp_set_welcome", chat_id=chat_id, enabled=enabled)
        return {"status": "updated", "chat_id": chat_id, "enabled": enabled}

    # ── confirm tier ──────────────────────────────────────────────────────

    @mcp.tool
    async def propose_ban(chat_id: int, user_id: int, reason: str = "") -> dict[str, Any]:
        """Ask a super admin to ban a user from one chat.

        Nothing happens until a human presses confirm in the moderator bot, and
        the request expires on its own if nobody does. Returns the pending id so
        you can tell the operator what is waiting for them.
        """
        return await _propose("ban", chat_id=chat_id, user_id=user_id, reason=reason)

    @mcp.tool
    async def propose_blacklist(user_id: int, reason: str = "") -> dict[str, Any]:
        """Ask a super admin to blacklist a user across every managed chat.

        The widest action available here, and the one least worth getting wrong,
        so it waits for a human press and expires unanswered.
        """
        return await _propose("blacklist", chat_id=None, user_id=user_id, reason=reason)


async def _propose(action: str, *, chat_id: int | None, user_id: int, reason: str) -> dict[str, Any]:
    from app.moderation.pending_actions import PendingActionService

    try:
        admin_id = initiator_id()
        bot = moderator_bot()
        async with session_maker()() as session:
            if chat_id is not None:
                await approved_chat_id(session, chat_id)
            pending = await PendingActionService(bot=bot, db=session).propose(
                origin="mcp",
                initiator_id=admin_id,
                action=action,
                target_user_id=user_id,
                chat_id=chat_id,
                reason=reason or None,
            )
            pending_id = pending.id
            expires_at = pending.expires_at.isoformat()
    except ToolError as err:
        return err.payload()

    logger.info("mcp_proposed", action=action, pending_id=pending_id, user_id=user_id)
    return {
        "status": "awaiting_confirmation",
        "pending_id": pending_id,
        "action": action,
        "user_id": user_id,
        "expires_at": expires_at,
    }
