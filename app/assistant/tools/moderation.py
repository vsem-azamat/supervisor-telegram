"""Moderation tools — mute, ban, blacklist."""

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps, _validate_chat_id
from app.core.logging import get_logger

logger = get_logger("assistant.tools.moderation")


def register_moderation_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register moderation tools on the agent."""

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

        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error

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
        """Add user to global blacklist and ban from all managed chats."""
        from app.moderation.blacklist import add_to_blacklist

        try:
            async with ctx.deps.session_maker() as session:
                await add_to_blacklist(session, ctx.deps.main_bot, user_id)
            return f"User {user_id} added to blacklist and banned from all managed chats."
        except Exception:
            logger.exception("blacklist_user_failed", user_id=user_id)
            return "Не удалось добавить в чёрный список. Проверьте логи бота."

    @agent.tool
    async def unblacklist_user(ctx: RunContext[AssistantDeps], user_id: int) -> str:
        """Remove user from global blacklist and unban from all managed chats."""
        from app.moderation.blacklist import remove_from_blacklist

        try:
            async with ctx.deps.session_maker() as session:
                await remove_from_blacklist(session, ctx.deps.main_bot, user_id)
            return f"User {user_id} removed from blacklist and unbanned from all managed chats."
        except Exception:
            logger.exception("unblacklist_user_failed", user_id=user_id)
            return "Не удалось убрать из чёрного списка. Проверьте логи бота."
