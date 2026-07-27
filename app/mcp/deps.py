"""Shared plumbing for MCP tools.

Tools take no context argument — FastMCP injects its own `Context`, not a
dependency container — so each one reaches for what it needs through here.

The peer resolver is the security-critical piece. Telethon runs on a real user
session, which can see every chat that account is in, including private
conversations that have nothing to do with moderation. Tools therefore resolve
a chat through :func:`managed_chat_id`, which refuses anything absent from the
`chats` table. The restriction is structural rather than a rule tools are asked
to follow: a tool that forgets to call it has no chat id to pass on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.config import settings

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.telethon.telethon_client import TelethonClient


class ToolError(Exception):
    """A refusal the caller should see, as opposed to an internal failure.

    Unhandled exceptions are masked before they reach the runtime, so anything
    the operator is meant to read has to travel as a returned payload instead.
    """

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.code}
        if self.detail:
            body["detail"] = self.detail
        return body


def session_maker() -> async_sessionmaker[AsyncSession]:
    from app.db.session import create_session_maker

    return create_session_maker()


def moderator_bot() -> Bot:
    """The moderator identity.

    Everything here acts in chats where the moderator bot is the administrator,
    and its dispatcher is the one holding the confirmation handlers, so a
    proposal sent under any other identity would show dead buttons.
    """
    from app.core.container import container

    bot = container.try_get_bot()
    if bot is None:
        raise ToolError("bot_unavailable")
    return bot


def telethon() -> TelethonClient:
    from app.core.container import container

    client = container.get_telethon_client()
    if client is None:
        raise ToolError("telethon_unavailable")
    return client


def initiator_id() -> int:
    """The admin this token acts as. Destructive tools refuse without it."""
    if not settings.mcp.initiator_id:
        raise ToolError("initiator_not_configured")
    return settings.mcp.initiator_id


async def managed_chat_id(session: AsyncSession, chat_id: int) -> int:
    """Return `chat_id` only if this deployment knows the chat at all.

    The gate that keeps a user session from being read as a general-purpose
    Telegram client. Deliberately admits chats awaiting approval: observing an
    unapproved group is allowed, which is how an operator decides about it.
    """
    from app.db.models import Chat

    found = await session.scalar(select(Chat.id).where(Chat.id == chat_id))
    if found is None:
        raise ToolError("unknown_chat")
    return found


async def approved_chat_id(session: AsyncSession, chat_id: int) -> int:
    """Return `chat_id` only if the chat is approved for public action.

    Reading an unapproved chat is fine; acting in one is not. Use this wherever
    the tool changes something a member would notice — the same rule the
    approval gate applies to updates arriving from Telegram.
    """
    from app.db.models import Chat

    status = await session.scalar(select(Chat.resource_status).where(Chat.id == chat_id))
    if status is None:
        raise ToolError("unknown_chat")
    if status != Chat.STATUS_APPROVED:
        raise ToolError("chat_not_approved", f"Chat {chat_id} is {status}; approve it before acting there.")
    return chat_id


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
