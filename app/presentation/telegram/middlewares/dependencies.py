from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.container import container


class DependenciesMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker[AsyncSession], bot: Bot):
        super().__init__()
        self.session_pool = session_pool
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["bot"] = self.bot
        async with self.session_pool() as session:
            data["db"] = session

            # Resolve repositories from container with current session
            data["admin_repo"] = container.get_admin_repository(session)
            data["user_repo"] = container.get_user_repository(session)
            data["chat_repo"] = container.get_chat_repository(session)
            data["chat_link_repo"] = container.get_chat_link_repository(session)
            data["message_repo"] = container.get_message_repository(session)

            # Application services resolved from container with current session
            data["spam_service"] = container.get_spam_service(session)
            data["user_service"] = container.get_user_service(session)
            data["moderation_service"] = container.get_moderation_service(session)

            return await handler(event, data)
