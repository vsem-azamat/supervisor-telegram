"""Channel management & pipeline tools."""

import re

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps, _validate_channel_id
from app.core.logging import get_logger

logger = get_logger("assistant.tools.channel")

_SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def register_channel_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register channel pipeline tools on the agent."""

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
                f"- {o.channel_id}: {status}, {o.channel.daily_posts_count} posts today, {len(o._pending_reviews)} pending reviews"
            )
        return "\n".join(lines)

    @agent.tool
    async def list_channels(ctx: RunContext[AssistantDeps]) -> str:
        """List all channels from the database with their config."""
        from sqlalchemy import select

        from app.infrastructure.db.models import Channel

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(Channel).order_by(Channel.id))
            channels = list(result.scalars().all())

        if not channels:
            return "Нет каналов в базе."

        lines = [f"Каналы ({len(channels)}):\n"]
        for ch in channels:
            status = "ON" if ch.enabled else "OFF"
            schedule = ", ".join(ch.posting_schedule) if ch.posting_schedule else "interval"
            lines.append(
                f"- [{status}] {ch.telegram_id} — {ch.name} ({ch.language})\n"
                f"  review: {ch.review_chat_id or 'нет'}, max: {ch.max_posts_per_day}/day, "
                f"schedule: {schedule}, today: {ch.daily_posts_count}"
            )
            if ch.description:
                lines.append(f"  desc: {ch.description[:80]}")
        return "\n".join(lines)

    @agent.tool
    async def add_channel(
        ctx: RunContext[AssistantDeps],
        telegram_id: str,
        name: str,
        description: str = "",
        language: str = "ru",
        review_chat_id: int = 0,
        max_posts_per_day: int = 3,
        posting_schedule: str = "",
        discovery_query: str = "",
        source_discovery_query: str = "",
    ) -> str:
        """Create a new channel. telegram_id: @username or numeric ID. posting_schedule: comma-separated HH:MM."""
        from app.agent.channel.channel_repo import create_channel

        if not (telegram_id.startswith("@") or telegram_id.lstrip("-").isdigit()):
            return "telegram_id должен быть @username или числовой ID."

        schedule_list = [t.strip() for t in posting_schedule.split(",") if t.strip()] or None
        try:
            ch = await create_channel(
                ctx.deps.session_maker,
                telegram_id=telegram_id,
                name=name,
                description=description,
                language=language,
                review_chat_id=review_chat_id or None,
                max_posts_per_day=max_posts_per_day,
                posting_schedule=schedule_list,
                discovery_query=discovery_query,
                source_discovery_query=source_discovery_query,
            )
            return f"Канал создан: {ch.telegram_id} — {ch.name} (id={ch.id})"
        except Exception:
            logger.exception("add_channel_failed", telegram_id=telegram_id)
            return "Не удалось создать канал. Возможно, такой telegram_id уже существует."

    @agent.tool
    async def edit_channel(
        ctx: RunContext[AssistantDeps],
        telegram_id: str,
        fields_json: str,
    ) -> str:
        """Update channel fields. fields_json is a JSON object with keys to update, e.g. '{"name": "New Name", "language": "cs", "enabled": true}'. Valid keys: name, description, language, review_chat_id, max_posts_per_day, posting_schedule, discovery_query, source_discovery_query, enabled."""
        import json

        from app.agent.channel.channel_repo import update_channel

        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError:
            return 'Неверный JSON. Пример: {"name": "New Name", "language": "cs"}'

        if not isinstance(fields, dict) or not fields:
            return "Укажите хотя бы одно поле для обновления."

        field_types: dict[str, type] = {
            "name": str,
            "description": str,
            "language": str,
            "review_chat_id": int,
            "max_posts_per_day": int,
            "posting_schedule": list,
            "discovery_query": str,
            "source_discovery_query": str,
            "enabled": bool,
            "username": str,
        }
        bad = set(fields) - set(field_types)
        if bad:
            return f"Недопустимые поля: {bad}. Допустимые: {set(field_types)}"

        for key, value in fields.items():
            expected = field_types[key]
            if not isinstance(value, expected):
                return f"Поле '{key}' должно быть {expected.__name__}, получено {type(value).__name__}"

        try:
            ch = await update_channel(ctx.deps.session_maker, telegram_id, **fields)
            if not ch:
                return f"Канал {telegram_id} не найден."
            return f"Канал {telegram_id} обновлён: {list(fields.keys())}"
        except Exception:
            logger.exception("edit_channel_failed", telegram_id=telegram_id)
            return "Не удалось обновить канал. Проверьте логи."

    @agent.tool
    async def remove_channel(ctx: RunContext[AssistantDeps], telegram_id: str) -> str:
        """Delete a channel from the DB. The orchestrator will stop it on next refresh."""
        from app.agent.channel.channel_repo import delete_channel

        ok = await delete_channel(ctx.deps.session_maker, telegram_id)
        if not ok:
            return f"Канал {telegram_id} не найден."
        return f"Канал {telegram_id} удалён. Оркестратор остановит его в течение 5 минут."

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
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                existing = await session.execute(
                    select(ChannelSource).where(ChannelSource.channel_id == channel_id, ChannelSource.url == url)
                )
                if existing.scalar_one_or_none():
                    return f"Source already exists for {channel_id}: {url}"

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
    async def remove_source(ctx: RunContext[AssistantDeps], url: str, channel_id: str) -> str:
        """Remove an RSS source by URL for a specific channel. channel_id is required."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(
                    select(ChannelSource).where(ChannelSource.channel_id == channel_id, ChannelSource.url == url)
                )
                source = result.scalar_one_or_none()
                if not source:
                    return f"Source not found: {url} for {channel_id}"
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
        """Set posting schedule. Format: comma-separated HH:MM times in UTC, e.g. '09:00,15:00,21:00'. Persists to DB."""
        times = [t.strip() for t in schedule.split(",") if t.strip()]
        for t in times:
            if not _SCHEDULE_TIME_RE.match(t):
                return f"Неверный формат времени: {t}. Используйте HH:MM (00:00-23:59)."

        from app.agent.channel.channel_repo import get_active_channels, update_channel

        if channel_id:
            ch = await update_channel(ctx.deps.session_maker, channel_id, posting_schedule=times)
            if not ch:
                return f"Канал {channel_id} не найден."
            updated = 1
        else:
            channels = await get_active_channels(ctx.deps.session_maker)
            updated = 0
            for ch in channels:
                await update_channel(ctx.deps.session_maker, ch.telegram_id, posting_schedule=times)
                updated += 1

        orch = ctx.deps.channel_orchestrator
        if orch:
            targets = orch.orchestrators
            if channel_id:
                targets = [o for o in targets if str(o.channel_id) == channel_id]
            for o in targets:
                o.channel.posting_schedule = times

        return f"Расписание обновлено: {times} для {updated} канал(ов). Сохранено в БД."
