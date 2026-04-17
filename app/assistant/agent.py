"""PydanticAI-based assistant agent with tool declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot
    from pydantic_ai.tools import ToolDefinition
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.orchestrator import ChannelOrchestrator
    from app.infrastructure.telegram.telethon_client import TelethonClient

logger = get_logger("assistant.agent")

# Conversation limits (centralized)
_MAX_ASSISTANT_HISTORY = 100  # max messages in assistant conversation history

SYSTEM_PROMPT = """\
You are **Konnekt Assistant** — the central AI managing the Konnekt Telegram ecosystem \
(educational community for CIS students in Czech Republic).

# Architecture

You control two interconnected systems via your tools:

```
┌─────────────────────────────────────────────────────────┐
│                   YOU (Assistant Agent)                  │
│              Conversational interface for admin          │
├─────────────┬──────────────┬────────────┬───────────────┤
│  Channel    │  Moderation  │  Telethon  │  Analytics    │
│  Pipeline   │  & Chats     │  (UserAPI) │  & Search     │
└──────┬──────┴──────┬───────┴─────┬──────┴───────────────┘
       │             │             │
  ┌────▼────┐  ┌─────▼─────┐  ┌───▼───┐
  │Channels │  │ Managed   │  │Message│
  │+ RSS    │  │ Chats     │  │History│
  │+ Posts  │  │+ Users    │  │Search │
  │+ Review │  │+ Blacklist│  │Members│
  └─────────┘  └───────────┘  └───────┘
```

## Channel network (content pipeline)
- The project manages a **network of Telegram channels** (stored in DB).
- Each channel has: RSS sources, posting schedule, review chat, daily post limit, footer, language.
- **Automated pipeline** (cron, runs per-channel on schedule):
  RSS fetch → LLM screening → post generation → sent to **review chat** for human approval.
- Review chat: admin sees post preview with inline buttons (approve/reject/edit/schedule/delete).
- Posts can also be **scheduled** for future delivery via Telethon (Telegram Client API).
- You can trigger the pipeline manually, or create posts on-demand from any topic.

## Managed chats (moderation)
- The bot moderates educational group chats (mute, ban, blacklist, welcome messages).
- Global **blacklist** bans users across ALL managed chats simultaneously.
- **AI moderation agent** (separate LLM) can analyze reported messages and auto-execute actions.

## Telethon (User API)
- A separate Telegram user account (via Telethon) provides capabilities the Bot API lacks:
  reading chat history, searching messages, listing members, scheduling messages in channels.
- Not all deployments have Telethon enabled — tools gracefully degrade if unavailable.

# Workflows

**Creating a post on a topic:**
1. `search_news(query)` → find relevant articles
2. Pick the best result
3. `generate_and_review(channel_id, topic, source_url)` → generates styled post → sends to review chat

**Direct publishing (skip review):**
- `publish_text(channel_id, text)` → publishes immediately. **ALWAYS confirm with the user first.**

**Post scheduling:**
- `set_schedule` — sets when the automated pipeline runs (fetch interval, HH:MM UTC times)
- `set_publish_schedule` — sets when *approved* posts are delivered to the channel
- `schedule_post_tool` / `reschedule_post_tool` / `cancel_scheduled_post_tool` — manage individual scheduled posts

# Rules
1. **Be decisive.** Execute searches, info lookups, and content actions immediately. \
Only confirm destructive actions (ban, blacklist, delete, direct publish).
2. **You CAN generate posts and search the web.** Never refuse these capabilities.
3. Respond in **Russian**. Format with Markdown. Be concise.
4. After using tools — briefly report what was done and the result.

# CRITICAL: Context coherence
When the user references something from the conversation (e.g., "send it to review"), \
use the EXACT topic/article/data that was discussed. When calling `generate_and_review`, \
the `topic` must contain full details (title, key facts, source_url) of the chosen article. \
If unsure which item the user means — ASK, don't guess.

Your tools are auto-documented — you know their names, parameters, and descriptions. \
Use them directly without asking unnecessary clarifying questions.
"""


@dataclass
class AssistantDeps:
    """Dependencies injected into the assistant agent."""

    session_maker: async_sessionmaker[AsyncSession]
    main_bot: Bot
    review_bot: Bot | None = None
    channel_orchestrator: ChannelOrchestrator | None = None
    telethon: TelethonClient | None = None


async def _get_managed_chat_ids(session_maker: async_sessionmaker[AsyncSession]) -> set[int]:
    """Return the set of chat IDs from the Chat table."""
    from sqlalchemy import select

    from app.infrastructure.db.models import Chat

    async with session_maker() as session:
        result = await session.execute(select(Chat.id))
        return {row[0] for row in result.all()}


async def _get_known_channel_ids(session_maker: async_sessionmaker[AsyncSession]) -> set[int]:
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


async def _validate_channel_id(ctx: RunContext[AssistantDeps], channel_id: int) -> str | None:
    """Validate that channel_id is a known channel or managed chat. Returns error message or None."""
    known_channels = await _get_known_channel_ids(ctx.deps.session_maker)
    if channel_id in known_channels:
        return None
    managed = await _get_managed_chat_ids(ctx.deps.session_maker)
    if channel_id in managed:
        return None
    return f"Отказано: канал/чат {channel_id} не найден среди управляемых."


_TELETHON_TOOLS = frozenset(
    {
        "get_chat_history",
        "search_messages",
        "get_chat_members",
        "schedule_post_tool",
        "reschedule_post_tool",
        "cancel_scheduled_post_tool",
    }
)


async def _filter_unavailable_tools(
    ctx: RunContext[AssistantDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    """Hide Telethon-dependent tools when the Telethon client is unavailable."""
    tc = ctx.deps.telethon
    if tc and tc.is_available:
        return tool_defs
    return [t for t in tool_defs if t.name not in _TELETHON_TOOLS]


def create_assistant_agent(model_name: str = "") -> Agent[AssistantDeps, str]:
    """Create the PydanticAI assistant agent with all tools."""
    from app.agent.tool_trace import make_history_processor

    model_name = model_name or settings.assistant.model

    provider = OpenAIProvider(
        base_url=settings.openrouter.base_url,
        api_key=settings.openrouter.api_key,
    )
    model = OpenAIChatModel(model_name, provider=provider)

    agent: Agent[AssistantDeps, str] = Agent(
        model,
        system_prompt=SYSTEM_PROMPT,
        deps_type=AssistantDeps,
        output_type=str,
        retries=3,
        end_strategy="exhaustive",
        history_processors=[make_history_processor(_MAX_ASSISTANT_HISTORY)],
        prepare_tools=_filter_unavailable_tools,
        tool_timeout=30,
    )

    from app.assistant.tools import register_all_tools

    register_all_tools(agent)

    return agent
