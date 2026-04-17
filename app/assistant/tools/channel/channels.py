"""Channel CRUD tools: list / add / edit / remove."""

from __future__ import annotations

from typing import TYPE_CHECKING

# RunContext + AssistantDeps kept at runtime — PydanticAI's @agent.tool
# decorator resolves tool-function type hints at registration time.
from pydantic_ai import RunContext  # noqa: TC002

from app.assistant.agent import AssistantDeps  # noqa: TC001
from app.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic_ai import Agent

logger = get_logger("assistant.tools.channel.channels")


def register_channels_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register channel CRUD tools on the agent."""

    @agent.tool
    async def list_channels(ctx: RunContext[AssistantDeps]) -> str:
        """List all channels from the database with their config."""
        from sqlalchemy import select

        from app.db.models import Channel

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
        telegram_id: int,
        name: str,
        description: str = "",
        language: str = "ru",
        review_chat_id: int = 0,
        max_posts_per_day: int = 3,
        posting_schedule: str = "",
        discovery_query: str = "",
        source_discovery_query: str = "",
        username: str = "",
    ) -> str:
        """Create a new channel. telegram_id: numeric Telegram chat ID (e.g. -1001234567890). posting_schedule: comma-separated HH:MM. username: optional @username without the @."""
        from app.channel.channel_repo import create_channel

        # Auto-resolve username from Bot API if not provided
        if not username:
            try:
                chat_info = await ctx.deps.main_bot.get_chat(telegram_id)
                username = (chat_info.username or "").lstrip("@")
            except Exception:
                logger.warning("add_channel_username_resolve_failed", telegram_id=telegram_id)

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
                username=username or None,
            )
            return f"Канал создан: {ch.telegram_id} — {ch.name} (id={ch.id})"
        except Exception:
            logger.exception("add_channel_failed", telegram_id=telegram_id)
            return "Не удалось создать канал. Возможно, такой telegram_id уже существует."

    @agent.tool
    async def edit_channel(
        ctx: RunContext[AssistantDeps],
        telegram_id: int,
        fields_json: str,
    ) -> str:
        """Update channel fields. fields_json is a JSON object with keys to update, e.g. '{"footer_template": "——\\n🔗 **Name** | @channel"}'. Valid keys: name, description, language, review_chat_id, max_posts_per_day, posting_schedule, publish_schedule, discovery_query, source_discovery_query, enabled, username, footer_template. Use footer_template for custom footer, publish_schedule for auto-scheduling (list of HH:MM UTC)."""
        import json

        from app.channel.channel_repo import update_channel

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
    async def remove_channel(ctx: RunContext[AssistantDeps], telegram_id: int) -> str:
        """Delete a channel from the DB. The orchestrator will stop it on next refresh."""
        from app.channel.channel_repo import delete_channel

        ok = await delete_channel(ctx.deps.session_maker, telegram_id)
        if not ok:
            return f"Канал {telegram_id} не найден."
        return f"Канал {telegram_id} удалён. Оркестратор остановит его в течение 5 минут."
