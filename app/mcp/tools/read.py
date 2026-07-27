"""Read-only moderation tools for the MCP control plane.

These are ports of the in-process assistant's read tools, with three changes
that the earlier home-grown surface did not need but this one does.

*Structured output.* The assistant returned prose because its only consumer was
a prompt. Here the consumer is an external runtime, so every tool returns an
explicit projection: named fields, no ORM rows, nothing that changes shape when
a column is added.

*Explicit gates.* Telethon runs on a user session that can see every chat the
account belongs to, private conversations included. Anything that touches it
resolves the chat through :func:`~app.mcp.deps.managed_chat_id` first, so a chat
this deployment does not manage has no id to hand on.

*Withheld fields.* A projection is also the place to decide what never leaves:
phone numbers from Telethon profiles, and the free-text rationale attached to
past moderation decisions. See the individual tools.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.mcp.deps import ToolError, clamp, managed_chat_id, moderator_bot, session_maker, telethon

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import FastMCP

    from app.telethon.telethon_client import ChatMember, MessageInfo, TelethonClient

logger = get_logger("mcp.tools.read")

# Message bodies are bounded so that a 100-message page cannot dominate the
# caller's context. Telegram allows 4096 characters per message.
_MAX_TEXT = 1000


def _guarded[**P](func: Callable[P, Awaitable[dict[str, Any]]]) -> Callable[P, Awaitable[dict[str, Any]]]:
    """Turn refusals and failures into payloads the caller can read.

    ``mask_error_details`` is on, so an exception that escapes a tool reaches the
    calling runtime as "internal error" — accurate for a bug, useless for
    "that chat is not managed here". Both travel as return values instead.
    """

    # getattr because a Callable is not necessarily a function; every tool here
    # is one, but the annotation does not promise it.
    name = getattr(func, "__name__", "unknown")

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except ToolError as err:
            return err.payload()
        except Exception:
            logger.exception("mcp_read_tool_failed", tool=name)
            return {"error": "tool_failed", "tool": name}

    return wrapper


def _live_telethon() -> TelethonClient:
    """The Telethon client, or a refusal when the session is not usable.

    Without this check its methods answer an empty list, which reads as "this
    chat is empty" rather than "nobody looked".
    """
    client = telethon()
    if not client.is_available:
        raise ToolError("telethon_unavailable", "The Telegram client session is not connected.")
    return client


def _chat_summary(chat: Any) -> dict[str, Any]:
    """Project a Chat row, keeping its approval state visible."""
    from app.db.models import Chat

    return {
        "chat_id": chat.id,
        "title": chat.title or "",
        # A row in `chats` is not an endorsement: discovered chats are ones the
        # bot merely saw, disabled ones were switched off. Callers that treat
        # every listed chat as in-scope would act on both.
        "resource_status": chat.resource_status,
        "is_approved": chat.resource_status == Chat.STATUS_APPROVED,
        "is_forum": chat.is_forum,
        "welcome_enabled": chat.is_welcome_enabled,
        "captcha_enabled": chat.is_captcha_enabled,
        "parent_chat_id": chat.parent_chat_id,
    }


def _user_summary(user: Any) -> dict[str, Any]:
    """Project a User row. Local DB only — no Telethon fields."""
    return {
        "user_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "blocked": user.blocked,
    }


def _iso(value: Any) -> str:
    return value.isoformat() if value is not None else ""


def _message_summary(message: MessageInfo) -> dict[str, Any]:
    text = message.text or ""
    return {
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "date": _iso(message.date),
        "text": text[:_MAX_TEXT],
        "text_truncated": len(text) > _MAX_TEXT,
        "reply_to_message_id": message.reply_to_msg_id,
    }


def _member_summary(member: ChatMember) -> dict[str, Any]:
    return {
        "user_id": member.user_id,
        "username": member.username or "",
        "first_name": member.first_name or "",
        "last_name": member.last_name or "",
    }


def register_read_tools(mcp: FastMCP[None]) -> None:
    """Register the read-only moderation toolset on an MCP server."""

    @mcp.tool
    @_guarded
    async def list_chats(limit: int = 100) -> dict[str, Any]:
        """List the chats this deployment knows about.

        Use this to resolve a chat title into the numeric chat_id every other
        tool needs. Read resource_status before acting: only "approved" chats
        are under moderation — "discovered" ones were merely seen by the bot and
        "disabled" ones were switched off, and neither should be acted on.

        limit caps how many chats to return (1-500), newest registrations last.
        """
        from sqlalchemy import func, select

        from app.db.models import Chat

        limit = clamp(limit, 1, 500)
        async with session_maker()() as session:
            total = (await session.execute(select(func.count()).select_from(Chat))).scalar() or 0
            rows = (await session.execute(select(Chat).order_by(Chat.id).limit(limit))).scalars().all()

        return {
            "chats": [_chat_summary(row) for row in rows],
            "returned": len(rows),
            "total": total,
        }

    @mcp.tool
    @_guarded
    async def get_blacklist(limit: int = 50) -> dict[str, Any]:
        """List users on the global blacklist — blocked from every managed chat.

        limit caps how many entries to return (1-200); compare `returned` with
        `total` to see whether the list was cut short. Ask for a larger page
        only when you actually need one, rather than dumping the whole table.
        """
        from sqlalchemy import func, select

        from app.db.models import User

        limit = clamp(limit, 1, 200)
        blocked = User.blocked.is_(True)
        async with session_maker()() as session:
            total = (await session.execute(select(func.count()).select_from(User).where(blocked))).scalar() or 0
            rows = (await session.execute(select(User).where(blocked).order_by(User.id).limit(limit))).scalars().all()

        return {
            "users": [_user_summary(row) for row in rows],
            "returned": len(rows),
            "total": total,
        }

    @mcp.tool
    @_guarded
    async def get_chat_info(chat_id: int) -> dict[str, Any]:
        """Get one chat's live details — title, type, member count, description.

        chat_id is the numeric Telegram ID from list_chats; chats absent from
        that list are refused. resource_status repeats the approval state, so
        you can tell a moderated chat from a merely discovered one.
        """
        from app.db.models import Chat

        async with session_maker()() as session:
            await managed_chat_id(session, chat_id)
            row = await session.get(Chat, chat_id)

        bot = moderator_bot()
        chat = await bot.get_chat(chat_id=chat_id)
        member_count = await bot.get_chat_member_count(chat_id=chat_id)

        info: dict[str, Any] = {
            "chat_id": chat.id,
            "title": chat.title or "",
            "type": chat.type,
            "username": chat.username or "",
            "member_count": member_count,
            "description": chat.description or "",
            "linked_chat_id": None,
            "resource_status": row.resource_status if row else "",
        }

        # Enrichment only: the Bot API answer is the one that matters, so a
        # failure here must not lose it.
        try:
            client = telethon()
            if client.is_available:
                full = await client.get_chat_info(chat_id)
                if full is not None:
                    info["description"] = info["description"] or (full.description or "")
                    info["linked_chat_id"] = full.linked_chat_id
        except Exception:
            logger.debug("mcp_telethon_enrichment_failed", chat_id=chat_id, exc_info=True)

        return info

    @mcp.tool
    @_guarded
    async def get_user_info(user_id: int) -> dict[str, Any]:
        """Get what is known about a user — names, bio, premium and blocked status.

        Works for users absent from the local database: known_locally tells you
        which fields came from our records. The user's phone number is never
        returned, whatever the Telegram profile exposes.
        """
        from sqlalchemy import select

        from app.db.models import User

        async with session_maker()() as session:
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

        info: dict[str, Any] = {
            "user_id": user_id,
            "known_locally": user is not None,
            "username": user.username or "" if user else "",
            "first_name": user.first_name or "" if user else "",
            "last_name": user.last_name or "" if user else "",
            "blocked": user.blocked if user else False,
            "bio": "",
            "is_bot": False,
            "is_premium": False,
            "photo_count": 0,
            "telethon_enriched": False,
        }

        try:
            client = telethon()
            if client.is_available:
                profile = await client.get_user_info(user_id)
                if profile is not None:
                    # Field-by-field on purpose. UserInfo carries `phone`, and
                    # any copy of the whole object would hand a phone number to
                    # an external runtime and from there into a chat log.
                    info["telethon_enriched"] = True
                    info["bio"] = profile.bio or ""
                    info["is_bot"] = profile.is_bot
                    info["is_premium"] = profile.is_premium
                    info["photo_count"] = profile.photo_count
                    info["username"] = info["username"] or (profile.username or "")
                    info["first_name"] = info["first_name"] or (profile.first_name or "")
                    info["last_name"] = info["last_name"] or (profile.last_name or "")
        except Exception:
            logger.debug("mcp_telethon_enrichment_failed", user_id=user_id, exc_info=True)

        return info

    @mcp.tool
    @_guarded
    async def get_moderation_history(user_id: int, limit: int = 10) -> dict[str, Any]:
        """Get a user's moderation record — how often reported, what was done.

        Use it before proposing an action, to tell a first-time report from a
        repeat offender. admin_overrides counts the times a human corrected the
        agent, which is the signal that its calls on this user were unreliable.

        Each past decision reports its action and whether an admin overrode it;
        the free-text rationale is withheld, since it is internal moderator
        reasoning and often quotes the message verbatim. limit caps how many
        decisions to return (1-50), newest first.
        """
        from app.moderation.memory import AgentMemory

        limit = clamp(limit, 1, 50)
        async with session_maker()() as session:
            memory = AgentMemory(session)
            profile = await memory.get_user_risk_profile(user_id)
            history = await memory.get_user_history(user_id, limit=limit)

        return {
            "user_id": user_id,
            "total_reports": profile.total_reports,
            "distinct_reporters": profile.distinct_reporters,
            "distinct_chats": profile.distinct_chats,
            "admin_overrides": profile.overridden_count,
            "actions": dict(profile.actions_taken),
            "last_action": profile.last_action or "",
            "decisions": [
                {
                    "decision_id": decision.id,
                    "chat_id": decision.chat_id,
                    "event_type": decision.event_type,
                    "action": decision.action,
                    "overridden": decision.admin_override is not None,
                    "created_at": _iso(decision.created_at),
                }
                for decision in history
            ],
        }

    @mcp.tool
    @_guarded
    async def get_chat_history(chat_id: int, limit: int = 20) -> dict[str, Any]:
        """Read recent messages from a managed chat, newest first.

        Use it to see the context around a report — what was said before and
        after. chat_id must come from list_chats; any other chat is refused.
        limit caps how many messages to return (1-100). Long message bodies are
        cut, flagged by text_truncated.
        """
        async with session_maker()() as session:
            await managed_chat_id(session, chat_id)

        limit = clamp(limit, 1, 100)
        messages = await _live_telethon().get_chat_history(chat_id, limit=limit)
        return {
            "chat_id": chat_id,
            "messages": [_message_summary(message) for message in messages],
            "returned": len(messages),
        }

    @mcp.tool
    @_guarded
    async def search_messages(chat_id: int, query: str, limit: int = 20) -> dict[str, Any]:
        """Search a managed chat's messages by text, newest first.

        Use it to check whether a phrase — a spam link, a repeated insult — has
        appeared before. chat_id must come from list_chats; any other chat is
        refused. limit caps how many matches to return (1-50).
        """
        async with session_maker()() as session:
            await managed_chat_id(session, chat_id)

        limit = clamp(limit, 1, 50)
        messages = await _live_telethon().search_messages(chat_id, query=query, limit=limit)
        return {
            "chat_id": chat_id,
            "query": query,
            "messages": [_message_summary(message) for message in messages],
            "returned": len(messages),
        }

    @mcp.tool
    @_guarded
    async def get_chat_members(chat_id: int, limit: int = 50) -> dict[str, Any]:
        """List members of a managed chat.

        Use it to resolve a display name or @username into the numeric user_id
        the moderation tools need. chat_id must come from list_chats; any other
        chat is refused. limit caps how many members to return (1-200), so on a
        large group this is a sample rather than the full roster.
        """
        async with session_maker()() as session:
            await managed_chat_id(session, chat_id)

        limit = clamp(limit, 1, 200)
        members = await _live_telethon().get_chat_members(chat_id, limit=limit)
        return {
            "chat_id": chat_id,
            "members": [_member_summary(member) for member in members],
            "returned": len(members),
        }
