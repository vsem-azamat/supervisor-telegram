"""Telethon-powered tools (Client API capabilities).

These tools are hidden by prepare_tools when Telethon is unavailable,
so tc is guaranteed non-None at runtime.
"""

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps, _validate_chat_id
from app.core.logging import get_logger

logger = get_logger("assistant.tools.telethon")


def register_telethon_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register Telethon-powered tools on the agent."""

    @agent.tool
    async def get_chat_history(ctx: RunContext[AssistantDeps], chat_id: str, limit: int = 20) -> str:
        """Read recent message history from a chat. Requires Client API (Telethon)."""
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error
        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        limit = min(max(1, limit), 100)
        try:
            messages = await tc.get_chat_history(int(chat_id), limit=limit)
            if not messages:
                return f"No messages found in {chat_id}."

            lines = [f"Last {len(messages)} messages in {chat_id}:\n"]
            for m in messages:
                sender = f"user:{m.sender_id}" if m.sender_id else "unknown"
                date = m.date.strftime("%m-%d %H:%M") if m.date else ""
                text = (m.text or "")[:100]
                lines.append(f"[{date}] {sender}: {text}")
            return "\n".join(lines)
        except Exception:
            logger.exception("get_chat_history_failed", chat_id=chat_id)
            return "Не удалось получить историю сообщений. Проверьте логи бота."

    @agent.tool
    async def search_messages(ctx: RunContext[AssistantDeps], chat_id: str, query: str, limit: int = 20) -> str:
        """Search for messages in a chat by text. Requires Client API (Telethon)."""
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error
        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        limit = min(max(1, limit), 50)
        try:
            messages = await tc.search_messages(int(chat_id), query=query, limit=limit)
            if not messages:
                return f"No messages matching '{query}' in {chat_id}."

            lines = [f"Found {len(messages)} messages matching '{query}':\n"]
            for m in messages:
                sender = f"user:{m.sender_id}" if m.sender_id else "unknown"
                date = m.date.strftime("%m-%d %H:%M") if m.date else ""
                text = (m.text or "")[:100]
                lines.append(f"[{date}] {sender}: {text}")
            return "\n".join(lines)
        except Exception:
            logger.exception("search_messages_failed", chat_id=chat_id, query=query)
            return "Не удалось найти сообщения. Проверьте логи бота."

    @agent.tool
    async def get_chat_members(ctx: RunContext[AssistantDeps], chat_id: str, limit: int = 50) -> str:
        """List members of a chat/group/channel. Requires Client API (Telethon)."""
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error
        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        limit = min(max(1, limit), 200)
        try:
            members = await tc.get_chat_members(int(chat_id), limit=limit)
            if not members:
                return f"No members found in {chat_id}."

            lines = [f"Members of {chat_id} ({len(members)} shown):\n"]
            for m in members:
                name = f"{m.first_name or ''} {m.last_name or ''}".strip() or "N/A"
                username = f"@{m.username}" if m.username else ""
                lines.append(f"- {m.user_id}: {name} {username}")
            return "\n".join(lines)
        except Exception:
            logger.exception("get_chat_members_failed", chat_id=chat_id)
            return "Не удалось получить список участников. Проверьте логи бота."
