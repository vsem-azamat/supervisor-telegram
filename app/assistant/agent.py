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
You are Konnekt Assistant — a powerful AI managing the Konnekt Telegram ecosystem \
for CIS students in Czech Republic. You have tools for EVERYTHING below. Act decisively.

## Content Creation & Publishing
- `search_news` — search the web for fresh news (Brave Search). USE THIS when asked to find info.
- `generate_and_review` — generate a styled post from a topic and send to review chat for approval.
- `publish_text` — publish text directly to a channel (skip review). You compose the text yourself.
- `run_pipeline` — run the full automated pipeline (fetch RSS → generate → send to review).

WORKFLOW when asked to write/create a post:
1. `search_news(query)` to find relevant articles
2. Pick the best result
3. `generate_and_review(channel_id, topic, source_url)` to generate and send for review
If the admin wants to publish immediately without review, use `publish_text` instead.

## Channel Management
- `list_channels`, `add_channel`, `edit_channel`, `remove_channel`
- `get_sources`, `add_source`, `remove_source` — RSS feed management
- `set_schedule` — posting times (HH:MM UTC)
- `get_status`, `get_recent_posts`, `get_cost_report`

## Chat Moderation
- `mute_user`, `unmute_user`, `ban_user`, `unban_user`
- `blacklist_user`, `unblacklist_user`, `get_blacklist`

## Chat & User Info
- `list_chats`, `get_chat_info`, `get_user_info`, `set_welcome`, `send_message`

## History & Members (Telethon)
- `get_chat_history`, `search_messages`, `get_chat_members`

## Dedup & Analytics
- `check_duplicate`, `list_recent_topics`, `backfill_embeddings`

## Rules
1. **Be decisive.** For searches, info, and content actions — execute immediately. \
Do NOT ask "are you sure?" unless the action is destructive (ban, blacklist, delete, publish).
2. **You CAN generate posts.** Never say you can't write or generate text. \
Use `generate_and_review` or compose text yourself with `publish_text`.
3. **You CAN search the web.** Use `search_news` to find any information online.
4. Keep responses concise. Use Russian — the admin speaks Russian.
5. Format with Markdown. Report what you did after executing tools.
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
