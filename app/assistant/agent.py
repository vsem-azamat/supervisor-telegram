"""PydanticAI-based assistant agent with tool declarations."""

from __future__ import annotations

import re
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
1. Channel content pipeline — sources, posts, scheduling, publishing
2. Chat moderation — mute, ban, unban users in any managed chat
3. User management — blacklist, user info (bio, last seen, premium), user lookup
4. Chat settings — welcome messages, full chat info (description, slow mode, linked chats)
5. Messaging — send messages to any chat or channel
6. Message history — read past messages, search in chats
7. Member management — list members, search members by name
8. Analytics — message view counts, forward counts

Use the tools to execute actions. Always report what you did.
Keep responses concise. Use Russian since the admin speaks Russian.
If unsure about a destructive action (ban, blacklist), confirm with the user first.
For read-only actions (status, info, list), execute immediately.

Format responses naturally with Markdown (bold, code, lists). Keep them clean and readable.
"""

_SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


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


def _get_known_channel_ids(orchestrator: ChannelOrchestrator | None) -> set[str]:
    """Return channel IDs from the orchestrator config."""
    if not orchestrator:
        return set()
    return {str(o.channel_id) for o in orchestrator.orchestrators}


async def _validate_chat_id(ctx: RunContext[AssistantDeps], chat_id: int) -> str | None:
    """Validate that chat_id is a managed chat. Returns error message or None."""
    managed = await _get_managed_chat_ids(ctx.deps.session_maker)
    if chat_id not in managed:
        return f"Отказано: чат {chat_id} не найден среди управляемых чатов."
    return None


async def _validate_channel_id(ctx: RunContext[AssistantDeps], channel_id: str) -> str | None:
    """Validate that channel_id is a known channel or managed chat. Returns error message or None."""
    known_channels = _get_known_channel_ids(ctx.deps.channel_orchestrator)
    if channel_id in known_channels:
        return None
    # Also allow numeric chat IDs that are managed
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

    # ------------------------------------------------------------------
    # Channel pipeline tools
    # ------------------------------------------------------------------

    @agent.tool
    async def get_status(ctx: RunContext[AssistantDeps]) -> str:
        """Get pipeline status for all channels — running/stopped, posts today, pending reviews."""
        orch = ctx.deps.channel_orchestrator
        if not orch:
            return "Channel orchestrator is not running."

        lines = ["Channel Pipeline Status:\n"]
        for o in orch.orchestrators:
            task_alive = o._task is not None and not o._task.done()
            status = "running" if task_alive else "stopped"
            lines.append(
                f"- {o.channel_id}: {status}, {o._posts_today} posts today, {len(o._pending_reviews)} pending reviews"
            )
        return "\n".join(lines)

    @agent.tool
    async def get_sources(ctx: RunContext[AssistantDeps], channel_id: str) -> str:
        """List RSS sources for a channel. channel_id is required — ask the user which channel."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelSource

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelSource).where(ChannelSource.channel_id == channel_id))
            sources = result.scalars().all()

        if not sources:
            return f"No sources found for {channel_id}."

        lines = [f"Sources for {channel_id} ({len(sources)} total):\n"]
        for s in sources:
            status = "on" if s.enabled else "OFF"
            lines.append(f"- [{status}] {s.title or s.url[:40]} (score: {s.relevance_score:.1f})")
        return "\n".join(lines)

    @agent.tool
    async def add_source(ctx: RunContext[AssistantDeps], url: str, channel_id: str, title: str = "") -> str:
        """Add a new RSS source for a channel. channel_id is required — ask the user which channel."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                existing = await session.execute(select(ChannelSource).where(ChannelSource.url == url))
                if existing.scalar_one_or_none():
                    return f"Source already exists: {url}"

                source = ChannelSource(
                    channel_id=channel_id,
                    url=url,
                    source_type="rss",
                    title=title or None,
                    added_by="assistant",
                )
                session.add(source)
                await session.commit()
            return f"Added source: {url} for {channel_id}"
        except Exception:
            logger.exception("add_source_failed", url=url, channel_id=channel_id)
            return "Не удалось добавить источник. Проверьте логи бота."

    @agent.tool
    async def remove_source(ctx: RunContext[AssistantDeps], url: str) -> str:
        """Remove an RSS source by URL."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(ChannelSource).where(ChannelSource.url == url))
                source = result.scalar_one_or_none()
                if not source:
                    return f"Source not found: {url}"
                await session.delete(source)
                await session.commit()
            return f"Removed source: {url}"
        except Exception:
            logger.exception("remove_source_failed", url=url)
            return "Не удалось удалить источник. Проверьте логи бота."

    @agent.tool
    async def run_pipeline(ctx: RunContext[AssistantDeps], channel_id: str = "") -> str:
        """Trigger content pipeline cycle now. Leave channel_id empty for all channels."""
        orch = ctx.deps.channel_orchestrator
        if not orch:
            return "Channel orchestrator is not running."
        try:
            await orch.run_once(channel_id or None)
        except Exception:
            logger.exception("run_pipeline_failed", channel_id=channel_id)
            return "Не удалось запустить пайплайн. Проверьте логи бота."
        return f"Pipeline cycle triggered for {channel_id or 'all channels'}."

    @agent.tool
    async def get_recent_posts(ctx: RunContext[AssistantDeps], channel_id: str, limit: int = 5) -> str:
        """Get recent posts from the database. channel_id is required — ask the user which channel."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelPost

        # Clamp limit to [1, 50]
        limit = min(max(1, limit), 50)

        async with ctx.deps.session_maker() as session:
            result = await session.execute(
                select(ChannelPost)
                .where(ChannelPost.channel_id == channel_id)
                .order_by(ChannelPost.id.desc())
                .limit(limit)
            )
            posts = result.scalars().all()

        if not posts:
            return f"No posts found for {channel_id}."

        lines = [f"Recent posts for {channel_id} (last {len(posts)}):\n"]
        for p in posts:
            title = p.title[:50] if p.title else "No title"
            lines.append(f"- [{p.status}] #{p.id}: {title}")
        return "\n".join(lines)

    @agent.tool
    async def get_cost_report(ctx: RunContext[AssistantDeps]) -> str:  # noqa: ARG001
        """Get LLM spending summary for current session."""
        try:
            from app.agent.channel.cost_tracker import get_session_summary

            summary = get_session_summary()
            return (
                f"LLM Cost Report (current session):\n"
                f"- Total cost: ${summary['total_cost_usd']:.4f}\n"
                f"- Total tokens: {summary['total_tokens']}\n"
                f"- Calls: {summary['total_calls']}\n"
                f"- By operation: {summary.get('by_operation', {})}"
            )
        except Exception:
            logger.exception("get_cost_report_failed")
            return "Не удалось получить отчёт о расходах. Проверьте логи бота."

    @agent.tool
    async def publish_text(ctx: RunContext[AssistantDeps], channel_id: str, text: str) -> str:
        """Publish a text message directly to a channel. Text supports Markdown formatting."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error
        try:
            from app.core.markdown import md_to_entities

            plain, entities = md_to_entities(text)
            msg = await ctx.deps.main_bot.send_message(chat_id=channel_id, text=plain, entities=entities)
            return f"Published to {channel_id}, message_id={msg.message_id}"
        except Exception:
            logger.exception("publish_text_failed", channel_id=channel_id)
            return "Не удалось опубликовать сообщение. Проверьте логи бота."

    @agent.tool
    async def set_schedule(ctx: RunContext[AssistantDeps], schedule: str, channel_id: str = "") -> str:
        """Set posting schedule. Format: comma-separated HH:MM times in UTC, e.g. '09:00,15:00,21:00'."""
        orch = ctx.deps.channel_orchestrator
        if not orch:
            return "Channel orchestrator is not running."

        times = [t.strip() for t in schedule.split(",") if t.strip()]
        for t in times:
            if not _SCHEDULE_TIME_RE.match(t):
                return f"Неверный формат времени: {t}. Используйте HH:MM (00:00-23:59)."

        targets = orch.orchestrators
        if channel_id:
            targets = [o for o in targets if str(o.channel_id) == channel_id]

        for o in targets:
            o.channel_config.posting_schedule = times
        return f"Schedule updated to {times} for {len(targets)} channel(s)."

    # ------------------------------------------------------------------
    # Moderation tools
    # ------------------------------------------------------------------

    @agent.tool
    async def list_chats(ctx: RunContext[AssistantDeps]) -> str:
        """List all managed chats with their settings."""
        from sqlalchemy import select

        from app.infrastructure.db.models import Chat

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(Chat))
            chats = result.scalars().all()

        if not chats:
            return "No managed chats."

        lines = ["Managed Chats:\n"]
        for c in chats:
            flags = []
            if c.is_welcome_enabled:
                flags.append("welcome ON")
            if c.is_captcha_enabled:
                flags.append("captcha ON")
            lines.append(f"- {c.id}: {c.title or 'No title'} {f'({", ".join(flags)})' if flags else ''}")
        return "\n".join(lines)

    @agent.tool
    async def mute_user(ctx: RunContext[AssistantDeps], chat_id: int, user_id: int, minutes: int = 5) -> str:
        """Mute a user in a chat for N minutes."""
        import datetime

        from aiogram.types import ChatPermissions

        # Validate chat_id
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error

        # Clamp minutes to [1, 43200] (1 min to 30 days)
        minutes = max(1, min(minutes, 43200))

        try:
            until_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)
            await ctx.deps.main_bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=until_date,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                ),
            )
            return f"Muted user {user_id} in {chat_id} for {minutes} minutes."
        except Exception:
            logger.exception("mute_user_failed", chat_id=chat_id, user_id=user_id)
            return "Не удалось замутить пользователя. Проверьте логи бота."

    @agent.tool
    async def unmute_user(ctx: RunContext[AssistantDeps], chat_id: int, user_id: int) -> str:
        """Unmute a user in a chat."""
        from aiogram.types import ChatPermissions

        # Validate chat_id
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error

        try:
            await ctx.deps.main_bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            return f"Unmuted user {user_id} in {chat_id}."
        except Exception:
            logger.exception("unmute_user_failed", chat_id=chat_id, user_id=user_id)
            return "Не удалось размутить пользователя. Проверьте логи бота."

    @agent.tool
    async def ban_user(ctx: RunContext[AssistantDeps], chat_id: int, user_id: int) -> str:
        """Ban a user from a chat."""
        # Validate chat_id
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error

        try:
            await ctx.deps.main_bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            return f"Banned user {user_id} from {chat_id}."
        except Exception:
            logger.exception("ban_user_failed", chat_id=chat_id, user_id=user_id)
            return "Не удалось забанить пользователя. Проверьте логи бота."

    @agent.tool
    async def unban_user(ctx: RunContext[AssistantDeps], chat_id: int, user_id: int) -> str:
        """Unban a user from a chat."""
        # Validate chat_id
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error

        try:
            await ctx.deps.main_bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            return f"Unbanned user {user_id} from {chat_id}."
        except Exception:
            logger.exception("unban_user_failed", chat_id=chat_id, user_id=user_id)
            return "Не удалось разбанить пользователя. Проверьте логи бота."

    @agent.tool
    async def get_blacklist(ctx: RunContext[AssistantDeps]) -> str:
        """Show all blacklisted (blocked) users."""
        from sqlalchemy import select

        from app.infrastructure.db.models import User

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(User).where(User.blocked == True))  # noqa: E712
            users = result.scalars().all()

        if not users:
            return "Blacklist is empty."

        lines = [f"Blacklisted Users ({len(users)} total):\n"]
        for u in users:
            lines.append(f"- {u.id}: {u.username or f'{u.first_name or ""} {u.last_name or ""}'.strip() or 'N/A'}")
        return "\n".join(lines)

    @agent.tool
    async def blacklist_user(ctx: RunContext[AssistantDeps], user_id: int) -> str:
        """Add user to global blacklist."""
        from sqlalchemy import select

        from app.infrastructure.db.models import User

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if not user:
                    return f"User {user_id} not found in DB."
                user.blocked = True
                await session.commit()
            return f"User {user_id} added to blacklist."
        except Exception:
            logger.exception("blacklist_user_failed", user_id=user_id)
            return "Не удалось добавить в чёрный список. Проверьте логи бота."

    @agent.tool
    async def unblacklist_user(ctx: RunContext[AssistantDeps], user_id: int) -> str:
        """Remove user from global blacklist."""
        from sqlalchemy import select

        from app.infrastructure.db.models import User

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if not user:
                    return f"User {user_id} not found in DB."
                user.blocked = False
                await session.commit()
            return f"User {user_id} removed from blacklist."
        except Exception:
            logger.exception("unblacklist_user_failed", user_id=user_id)
            return "Не удалось убрать из чёрного списка. Проверьте логи бота."

    @agent.tool
    async def send_message(ctx: RunContext[AssistantDeps], chat_id: str, text: str) -> str:
        """Send a message to any managed chat or known channel. Supports Markdown formatting."""
        # Validate: must be a managed chat or known channel
        error = await _validate_channel_id(ctx, chat_id)
        if error:
            return error

        try:
            from app.core.markdown import md_to_entities

            plain, entities = md_to_entities(text)
            msg = await ctx.deps.main_bot.send_message(chat_id=chat_id, text=plain, entities=entities)
            return f"Sent to {chat_id}, message_id={msg.message_id}"
        except Exception:
            logger.exception("send_message_failed", chat_id=chat_id)
            return "Не удалось отправить сообщение. Проверьте логи бота."

    @agent.tool
    async def get_chat_info(ctx: RunContext[AssistantDeps], chat_id: str) -> str:
        """Get full info about a Telegram chat — title, type, members, description, linked chat, slow mode."""
        try:
            # Basic info from Bot API
            chat = await ctx.deps.main_bot.get_chat(chat_id=chat_id)
            members = await ctx.deps.main_bot.get_chat_member_count(chat_id=chat_id)
            lines = [
                "Chat Info:",
                f"- ID: {chat.id}",
                f"- Title: {chat.title or 'N/A'}",
                f"- Type: {chat.type}",
                f"- Members: {members}",
                f"- Username: @{chat.username or 'N/A'}",
            ]
            if chat.description:
                lines.append(f"- Description: {chat.description}")

            # Enrich with Telethon (Client API) data
            tc = ctx.deps.telethon
            if tc and tc.is_available:
                try:
                    full = await tc.get_chat_info(chat.id)
                    if full:
                        if full.description and not chat.description:
                            lines.append(f"- Description: {full.description}")
                        if full.linked_chat_id:
                            lines.append(f"- Linked chat: {full.linked_chat_id}")
                except Exception:
                    logger.debug("telethon_enrichment_failed", exc_info=True)

            return "\n".join(lines)
        except Exception:
            logger.exception("get_chat_info_failed", chat_id=chat_id)
            return "Не удалось получить информацию о чате. Проверьте логи бота."

    @agent.tool
    async def set_welcome(ctx: RunContext[AssistantDeps], chat_id: int, message: str = "", enabled: bool = True) -> str:
        """Set or toggle welcome message for a chat."""
        from sqlalchemy import select

        from app.infrastructure.db.models import Chat

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(Chat).where(Chat.id == chat_id))
                chat = result.scalar_one_or_none()
                if not chat:
                    return f"Chat {chat_id} not found in DB."
                chat.is_welcome_enabled = enabled
                if message:
                    chat.welcome_message = message
                await session.commit()

            return f"Welcome {'enabled' if enabled else 'disabled'} for chat {chat_id}."
        except Exception:
            logger.exception("set_welcome_failed", chat_id=chat_id)
            return "Не удалось обновить приветственное сообщение. Проверьте логи бота."

    @agent.tool
    async def get_user_info(ctx: RunContext[AssistantDeps], user_id: int) -> str:
        """Get full user info — name, username, bio, premium status, blocked status."""
        from sqlalchemy import select

        from app.infrastructure.db.models import User

        try:
            lines = [f"User {user_id}:"]

            # DB info
            async with ctx.deps.session_maker() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

            if user:
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "N/A"
                lines.append(f"- Name: {name}")
                lines.append(f"- Username: @{user.username or 'N/A'}")
                lines.append(f"- Blocked: {user.is_blocked}")
            else:
                lines.append("- Not in local DB")

            # Enrich with Telethon (Client API) data — bio, premium, photo count
            tc = ctx.deps.telethon
            if tc and tc.is_available:
                try:
                    tg_user = await tc.get_user_info(user_id)
                    if tg_user:
                        if tg_user.bio:
                            lines.append(f"- Bio: {tg_user.bio}")
                        lines.append(f"- Premium: {'yes' if tg_user.is_premium else 'no'}")
                        lines.append(f"- Photos: {tg_user.photo_count}")
                        if not user and tg_user.first_name:
                            name = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip()
                            lines.insert(1, f"- Name (Telegram): {name}")
                            if tg_user.username:
                                lines.insert(2, f"- Username: @{tg_user.username}")
                except Exception:
                    logger.debug("telethon_enrichment_failed", exc_info=True)

            return "\n".join(lines)
        except Exception:
            logger.exception("get_user_info_failed", user_id=user_id)
            return "Не удалось получить информацию о пользователе. Проверьте логи бота."

    # ------------------------------------------------------------------
    # Telethon-powered tools (Client API capabilities)
    # ------------------------------------------------------------------

    @agent.tool
    async def get_chat_history(ctx: RunContext[AssistantDeps], chat_id: str, limit: int = 20) -> str:
        """Read recent message history from a chat. Requires Client API (Telethon)."""
        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available."

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
        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available."

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
        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available."

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

    return agent
