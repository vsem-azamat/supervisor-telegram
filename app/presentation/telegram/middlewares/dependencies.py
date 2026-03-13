from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.repositories import (
    get_admin_repository,
    get_chat_link_repository,
    get_chat_repository,
    get_message_repository,
    get_user_repository,
)
from app.moderation.user_service import UserService


class DependenciesMiddleware(BaseMiddleware):
    def __init__(
        self,
        session_pool: async_sessionmaker[AsyncSession],
        bot: Bot,
    ):
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
            data["admin_repo"] = get_admin_repository(session)
            data["user_repo"] = get_user_repository(session)
            data["chat_repo"] = get_chat_repository(session)
            data["chat_link_repo"] = get_chat_link_repository(session)
            data["message_repo"] = get_message_repository(session)
            data["user_service"] = UserService(get_user_repository(session))
            return await handler(event, data)
