"""PydanticAI-based assistant agent with tool declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.orchestrator import ChannelOrchestrator
    from app.infrastructure.telegram.telethon_client import TelethonClient

logger = get_logger("assistant.agent")

SYSTEM_PROMPT = """\
You are Konnekt Assistant — a powerful AI that manages the entire Konnekt Telegram ecosystem \
for CIS students in Czech Republic.

You have FULL control over:
1. Channel management — add/edit/remove channels, configure language/schedule/review chat
2. Channel content pipeline — sources, posts, scheduling, publishing
3. Chat moderation — mute, ban, unban users in any managed chat
4. User management — blacklist, user info (bio, last seen, premium), user lookup
5. Chat settings — welcome messages, full chat info (description, slow mode, linked chats)
6. Messaging — send messages to any chat or channel
7. Message history — read past messages, search in chats
8. Member management — list members, search members by name
9. Analytics — message view counts, forward counts
10. Dedup & search — check duplicates, list recent topics, backfill embeddings, web search via Brave

Use the tools to execute actions. Always report what you did.
Keep responses concise. Use Russian since the admin speaks Russian.
If unsure about a destructive action (ban, blacklist), confirm with the user first.
For read-only actions (status, info, list), execute immediately.

Format responses naturally with Markdown (bold, code, lists). Keep them clean and readable.
"""


@dataclass
class AssistantDeps:
    """Dependencies injected into the assistant agent."""

    session_maker: async_sessionmaker[AsyncSession]
    main_bot: Bot
    channel_orchestrator: ChannelOrchestrator | None = None
    telethon: TelethonClient | None = None


async def _get_managed_chat_ids(session_maker: async_sessionmaker[AsyncSession]) -> set[int]:
    """Return the set of chat IDs from the Chat table."""
    from sqlalchemy import select

    from app.infrastructure.db.models import Chat

    async with session_maker() as session:
        result = await session.execute(select(Chat.id))
        return {row[0] for row in result.all()}


async def _get_known_channel_ids(session_maker: async_sessionmaker[AsyncSession]) -> set[str]:
    """Return channel IDs from the DB channels table."""
    from sqlalchemy import select

    from app.infrastructure.db.models import Channel

    async with session_maker() as session:
        result = await session.execute(select(Channel.telegram_id))
        return {row[0] for row in result.all()}


async def _validate_chat_id(ctx: RunContext[AssistantDeps], chat_id: int | str) -> str | None:
    """Validate that chat_id is a managed chat. Returns error message or None."""
    managed = await _get_managed_chat_ids(ctx.deps.session_maker)
    try:
        numeric_id = int(chat_id)
    except (ValueError, TypeError):
        return f"Отказано: некорректный chat_id '{chat_id}'."
    if numeric_id not in managed:
        return f"Отказано: чат {chat_id} не найден среди управляемых чатов."
    return None


async def _validate_channel_id(ctx: RunContext[AssistantDeps], channel_id: str) -> str | None:
    """Validate that channel_id is a known channel or managed chat. Returns error message or None."""
    known_channels = await _get_known_channel_ids(ctx.deps.session_maker)
    if channel_id in known_channels:
        return None
    try:
        cid = int(channel_id)
        managed = await _get_managed_chat_ids(ctx.deps.session_maker)
        if cid in managed:
            return None
    except ValueError:
        pass
    return f"Отказано: канал/чат {channel_id} не найден среди управляемых."


def create_assistant_agent(model_name: str = "") -> Agent[AssistantDeps, str]:
    """Create the PydanticAI assistant agent with all tools."""
    model_name = model_name or "anthropic/claude-sonnet-4-6"

    provider = OpenAIProvider(
        base_url=settings.agent.openrouter_base_url,
        api_key=settings.agent.openrouter_api_key,
    )
    model = OpenAIModel(model_name, provider=provider)

    agent: Agent[AssistantDeps, str] = Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        deps_type=AssistantDeps,
        output_type=str,
    )

    from app.assistant.tools import register_all_tools

    register_all_tools(agent)

    return agent
