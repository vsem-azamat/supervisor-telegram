"""Pipeline tools: status, trigger, posts, cost, publish, generate-and-review."""

from __future__ import annotations

from typing import TYPE_CHECKING

# RunContext + AssistantDeps kept at runtime — PydanticAI's @agent.tool
# decorator resolves tool-function type hints at registration time.
from pydantic_ai import RunContext  # noqa: TC002

from app.assistant.agent import AssistantDeps, _validate_channel_id  # noqa: TC001
from app.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic_ai import Agent

logger = get_logger("assistant.tools.channel.pipeline")


def register_pipeline_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register pipeline/content tools on the agent."""

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
    async def run_pipeline(ctx: RunContext[AssistantDeps], channel_id: int = 0) -> str:
        """Run the automated content pipeline: fetches news from RSS, generates posts via LLM, sends drafts to review chat. Leave channel_id as 0 for all channels."""
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
    async def get_recent_posts(ctx: RunContext[AssistantDeps], channel_id: int, limit: int = 5) -> str:
        """Get recent posts from the database for a channel."""
        from sqlalchemy import select

        from app.db.models import ChannelPost

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
            from app.channel.cost_tracker import get_session_summary

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
    async def publish_text(ctx: RunContext[AssistantDeps], channel_id: int, text: str) -> str:
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
    async def generate_and_review(
        ctx: RunContext[AssistantDeps],
        channel_id: int,
        topic: str,
        source_url: str = "",
    ) -> str:
        """Generate a styled post from a topic and send it for admin review. Use after search_news to turn a found article into a post. IMPORTANT: topic must contain the FULL details of the specific news story — title, key facts, context. Do NOT pass a vague summary. source_url: the article URL from search results (pass it!)."""
        from hashlib import sha256

        from sqlalchemy import select

        from app.channel.config import language_name
        from app.channel.exceptions import GenerationError
        from app.channel.generator import generate_post as _generate
        from app.channel.sources import ContentItem
        from app.core.config import settings
        from app.db.models import Channel

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

        api_key = settings.openrouter.api_key
        gen_model = settings.channel.generation_model
        lang = language_name(channel.language)

        channel_context = ""
        if channel.discovery_query:
            channel_context = f"Channel focus: {channel.discovery_query}"

        try:
            post = await _generate(
                [item],
                api_key=api_key,
                model=gen_model,
                language=lang,
                footer=channel.footer,
                channel_name=channel.name,
                channel_context=channel_context,
                channel_id=channel_id,
                session_maker=ctx.deps.session_maker,
                vision_model=settings.channel.vision_model,
                phash_threshold=settings.channel.image_phash_threshold,
                phash_lookback=settings.channel.image_phash_lookback_posts,
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
            from app.channel.review import send_for_review as _send_review

            try:
                post_id = await _send_review(
                    bot=ctx.deps.review_bot or ctx.deps.main_bot,
                    review_chat_id=review_chat_id,
                    channel_id=channel_id,
                    post=post,
                    source_items=[item],
                    session_maker=ctx.deps.session_maker,
                    api_key=api_key,
                    embedding_model=settings.channel.embedding_model,
                    channel_name=channel.name,
                    channel_username=channel.username,
                )
            except Exception:
                logger.exception("generate_and_review_send_failed", channel_id=channel_id)
                return "Пост сгенерирован, но не удалось отправить на ревью."

            if not post_id:
                return "Пост сгенерирован, но отправка на ревью не удалась."

            preview = post.text[:300] + ("..." if len(post.text) > 300 else "")
            return f"Пост #{post_id} отправлен на ревью.\n\nПревью:\n{preview}"
        from app.channel.publisher import publish_post as _publish

        try:
            msg_id = await _publish(ctx.deps.main_bot, channel.telegram_id, post)
        except Exception:
            logger.exception("generate_and_review_publish_failed", channel_id=channel_id)
            return "Пост сгенерирован, но публикация не удалась."

        if not msg_id:
            return "Пост сгенерирован, но публикация не удалась."

        preview = post.text[:300] + ("..." if len(post.text) > 300 else "")
        return f"Пост опубликован (нет review_chat_id). msg_id={msg_id}\n\nПревью:\n{preview}"
