"""Chat & user info tools."""

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps, _validate_channel_id, _validate_chat_id
from app.core.logging import get_logger

logger = get_logger("assistant.tools.chat")


def register_chat_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register chat & user info tools on the agent."""

    @agent.tool
    async def send_message(ctx: RunContext[AssistantDeps], chat_id: str, text: str) -> str:
        """Send a message to any managed chat or known channel. Supports Markdown formatting."""
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
        error = await _validate_chat_id(ctx, chat_id)
        if error:
            return error
        try:
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
