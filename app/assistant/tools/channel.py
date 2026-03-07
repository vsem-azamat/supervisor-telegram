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
            pub_schedule = ", ".join(ch.publish_schedule) if ch.publish_schedule else "immediate"
            username_str = f"@{ch.username}" if ch.username else "no username"
            lines.append(
                f"- [{status}] {ch.telegram_id} ({username_str}) — {ch.name} ({ch.language})\n"
                f"  review: {ch.review_chat_id or 'нет'}, max: {ch.max_posts_per_day}/day, "
                f"schedule: {schedule}, publish: {pub_schedule}, today: {ch.daily_posts_count}\n"
                f"  footer: {ch.footer}"
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
        """Update channel fields. fields_json is a JSON object with keys to update, e.g. '{"footer_template": "——\\n🔗 **Name** | @channel"}'. Valid keys: name, description, language, review_chat_id, max_posts_per_day, posting_schedule, publish_schedule, discovery_query, source_discovery_query, enabled, username, footer_template. Use footer_template for custom footer, publish_schedule for auto-scheduling (list of HH:MM UTC)."""
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
            "publish_schedule": list,
            "discovery_query": str,
            "source_discovery_query": str,
            "enabled": bool,
            "username": str,
            "footer_template": str,
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
        """List RSS sources for a channel. Use list_channels first if unsure about channel_id."""
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
        """Add a new RSS source for a channel."""
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
        """Run the automated content pipeline: fetches news from RSS, generates posts via LLM, sends drafts to review chat. Leave channel_id empty for all channels."""
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
        """Get recent posts from the database for a channel."""
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
            cache_read = summary.get("cache_read_tokens", 0)
            cache_write = summary.get("cache_write_tokens", 0)
            cache_savings = summary.get("cache_savings_usd", 0.0)

            lines = [
                "LLM Cost Report (current session):\n",
                f"- Total cost: ${summary['total_cost_usd']:.4f}",
                f"- Total tokens: {summary['total_tokens']}",
                f"- Calls: {summary['total_calls']}",
            ]

            if cache_read or cache_write:
                lines.append("\nCache stats:")
                lines.append(f"- Cache read tokens: {cache_read}")
                lines.append(f"- Cache write tokens: {cache_write}")
                lines.append(f"- Cache savings: ${cache_savings:.4f}")
                if summary["total_cost_usd"] > 0:
                    pct = (cache_savings / (summary["total_cost_usd"] + cache_savings)) * 100
                    lines.append(f"- Savings rate: {pct:.1f}%")

            ops = summary.get("by_operation", {})
            if ops:
                lines.append("\nBy operation:")
                for op, data in ops.items():
                    sav = data.get("cache_savings_usd", 0)
                    sav_str = f", saved ${sav:.4f}" if sav else ""
                    lines.append(f"- {op}: {data['calls']} calls, ${data['cost_usd']:.4f}{sav_str}")

            return "\n".join(lines)
        except Exception:
            logger.exception("get_cost_report_failed")
            return "Не удалось получить отчёт о расходах. Проверьте логи бота."

    @agent.tool
    async def publish_text(ctx: RunContext[AssistantDeps], channel_id: str, text: str) -> str:
        """Publish text directly to a channel, skipping review. You compose the text yourself. Supports Markdown. IMPORTANT: This is a destructive action — ALWAYS ask the user for explicit confirmation before calling this tool. Explain what will be published and to which channel, and wait for a clear 'yes' or confirmation."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error
        try:
            from app.core.markdown import md_to_entities

            plain, entities = md_to_entities(text)
            msg = await ctx.deps.main_bot.send_message(
                chat_id=channel_id, text=plain, entities=entities, parse_mode=None
            )
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

    @agent.tool
    async def generate_and_review(
        ctx: RunContext[AssistantDeps],
        channel_id: str,
        topic: str,
        source_url: str = "",
    ) -> str:
        """Generate a styled post from a topic and send it for admin review. Use after search_news to turn a found article into a post. IMPORTANT: topic must contain the FULL details of the specific news story — title, key facts, context. Do NOT pass a vague summary. source_url: the article URL from search results (pass it!)."""
        from hashlib import sha256

        from sqlalchemy import select

        from app.agent.channel.config import language_name
        from app.agent.channel.exceptions import GenerationError
        from app.agent.channel.generator import generate_post as _generate
        from app.agent.channel.sources import ContentItem
        from app.core.config import settings
        from app.infrastructure.db.models import Channel

        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        if not topic.strip():
            return "Укажите тему или текст для генерации поста."

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(Channel).where(Channel.telegram_id == channel_id))
            channel = result.scalar_one_or_none()

        if not channel:
            return f"Канал {channel_id} не найден в базе."

        ext_id = sha256(f"{channel_id}:{topic[:100]}".encode()).hexdigest()[:16]
        item = ContentItem(
            source_url=source_url or "assistant",
            external_id=ext_id,
            title=topic[:200],
            body=topic,
            url=source_url or None,
        )

        api_key = settings.agent.openrouter_api_key
        gen_model = settings.channel.generation_model
        lang = language_name(channel.language)

        try:
            post = await _generate(
                [item],
                api_key=api_key,
                model=gen_model,
                language=lang,
                footer=channel.footer,
            )
        except GenerationError:
            logger.exception("generate_and_review_failed", channel_id=channel_id)
            return "Не удалось сгенерировать пост. Проверьте логи."
        except Exception:
            logger.exception("generate_and_review_failed", channel_id=channel_id)
            return "Не удалось сгенерировать пост. Проверьте логи."

        if not post:
            return "Генерация не вернула результат. Попробуйте другую тему."

        review_chat_id = channel.review_chat_id
        if review_chat_id:
            from app.agent.channel.review import send_for_review as _send_review

            try:
                post_id = await _send_review(
                    bot=ctx.deps.main_bot,
                    review_chat_id=review_chat_id,
                    channel_id=channel_id,
                    post=post,
                    source_items=[item],
                    session_maker=ctx.deps.session_maker,
                    api_key=api_key,
                    embedding_model=settings.channel.embedding_model,
                    channel_name=channel.name,
                    channel_username=channel.username,
                    has_publish_schedule=bool(channel.publish_schedule),
                )
            except Exception:
                logger.exception("generate_and_review_send_failed", channel_id=channel_id)
                return "Пост сгенерирован, но не удалось отправить на ревью."

            if not post_id:
                return "Пост сгенерирован, но отправка на ревью не удалась."

            preview = post.text[:300] + ("..." if len(post.text) > 300 else "")
            return f"Пост #{post_id} отправлен на ревью.\n\nПревью:\n{preview}"
        from app.agent.channel.publisher import publish_post as _publish

        try:
            msg_id = await _publish(ctx.deps.main_bot, channel.telegram_id, post)
        except Exception:
            logger.exception("generate_and_review_publish_failed", channel_id=channel_id)
            return "Пост сгенерирован, но публикация не удалась."

        if not msg_id:
            return "Пост сгенерирован, но публикация не удалась."

        preview = post.text[:300] + ("..." if len(post.text) > 300 else "")
        return f"Пост опубликован (нет review_chat_id). msg_id={msg_id}\n\nПревью:\n{preview}"

    @agent.tool
    async def list_scheduled(ctx: RunContext[AssistantDeps], channel_id: str = "") -> str:
        """List all currently scheduled (not yet published) posts. Leave channel_id empty for all channels."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelPost

        query = select(ChannelPost).where(ChannelPost.status == "scheduled").order_by(ChannelPost.scheduled_at)
        if channel_id:
            query = query.where(ChannelPost.channel_id == channel_id)

        async with ctx.deps.session_maker() as session:
            result = await session.execute(query)
            posts = result.scalars().all()

        if not posts:
            return "Нет запланированных постов."

        lines = [f"Scheduled posts ({len(posts)}):\n"]
        for p in posts:
            time_str = p.scheduled_at.strftime("%d %b %H:%M UTC") if p.scheduled_at else "?"
            lines.append(f"- #{p.id} [{p.channel_id}] {time_str}: {p.title[:50]}")
        return "\n".join(lines)

    @agent.tool
    async def schedule_post_tool(
        ctx: RunContext[AssistantDeps],
        post_id: int,
        time: str = "",
    ) -> str:
        """Schedule a draft post for future delivery. time format: 'YYYY-MM-DD HH:MM' UTC, or empty for next available slot. IMPORTANT: Ask for confirmation first."""
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available for scheduling."

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        if time:
            try:
                publish_time = dt.strptime(time, "%Y-%m-%d %H:%M")
            except ValueError:
                return "Invalid time format. Use 'YYYY-MM-DD HH:MM' UTC."
        elif channel.publish_schedule:
            from app.agent.channel.schedule_manager import get_occupied_slots, next_publish_slot

            occupied = await get_occupied_slots(ctx.deps.session_maker, channel.telegram_id)
            try:
                publish_time = next_publish_slot(channel.publish_schedule, occupied)
            except ValueError:
                return "No available publish slots."
        else:
            return "No time specified and no publish_schedule configured for this channel."

        from app.agent.channel.schedule_manager import schedule_post

        return await schedule_post(tc, ctx.deps.session_maker, post_id, channel, publish_time)

    @agent.tool
    async def reschedule_post_tool(
        ctx: RunContext[AssistantDeps],
        post_id: int,
        new_time: str,
    ) -> str:
        """Reschedule an already-scheduled post. Format: 'YYYY-MM-DD HH:MM' UTC."""
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available."

        try:
            publish_time = dt.strptime(new_time, "%Y-%m-%d %H:%M")
        except ValueError:
            return "Invalid time format. Use 'YYYY-MM-DD HH:MM' UTC."

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        from app.agent.channel.schedule_manager import reschedule_post

        return await reschedule_post(tc, ctx.deps.session_maker, post_id, channel, publish_time)

    @agent.tool
    async def cancel_scheduled_post_tool(ctx: RunContext[AssistantDeps], post_id: int) -> str:
        """Cancel a scheduled post — removes from Telegram queue, reverts to draft."""
        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        if not tc or not tc.is_available:
            return "Telethon client not available."

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        from app.agent.channel.schedule_manager import cancel_scheduled_post

        return await cancel_scheduled_post(tc, ctx.deps.session_maker, post_id, channel)

    @agent.tool
    async def set_publish_schedule(
        ctx: RunContext[AssistantDeps],
        channel_id: str,
        schedule: str,
    ) -> str:
        """Set when approved posts go live. Format: comma-separated HH:MM UTC, e.g. '09:00,13:00,18:00'. Empty string disables scheduling (posts publish immediately on approve)."""
        from app.agent.channel.channel_repo import update_channel

        times = [t.strip() for t in schedule.split(",") if t.strip()] if schedule else []
        for t in times:
            if not _SCHEDULE_TIME_RE.match(t):
                return f"Invalid time format: {t}. Use HH:MM (00:00-23:59)."

        ch = await update_channel(ctx.deps.session_maker, channel_id, publish_schedule=times or None)
        if not ch:
            return f"Channel {channel_id} not found."

        if times:
            return f"Publish schedule set: {times} for {channel_id}. Approved posts will be scheduled."
        return f"Publish schedule cleared for {channel_id}. Posts will publish immediately on approve."
