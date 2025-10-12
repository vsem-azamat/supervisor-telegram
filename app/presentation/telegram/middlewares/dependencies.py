from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.moderation_service import ModerationService
from app.application.services.spam import SpamService
from app.application.services.user_service import UserService
from app.core.container import container
from app.infrastructure.db.repositories import (
    get_admin_repository,
    get_chat_link_repository,
    get_chat_repository,
    get_message_repository,
    get_user_repository,
)


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
            admin_repo = get_admin_repository(session)
            user_repo = get_user_repository(session)
            chat_repo = get_chat_repository(session)
            chat_link_repo = get_chat_link_repository(session)
            message_repo = get_message_repository(session)

            data["admin_repo"] = admin_repo
            data["user_repo"] = user_repo
            data["chat_repo"] = chat_repo
            data["chat_link_repo"] = chat_link_repo
            data["message_repo"] = message_repo

            # Application services
            spam_service = SpamService(message_repo)
            moderation_service = ModerationService(
                bot=self.bot,
                chat_repository=chat_repo,
                message_repository=message_repo,
                user_repository=user_repo,
                spam_service=spam_service,
            )
            agent_service = container.get_agent_service()

            data["spam_service"] = spam_service
            data["moderation_service"] = moderation_service
            data["user_service"] = UserService(user_repo)
            data["agent_service"] = agent_service
            return await handler(event, data)
