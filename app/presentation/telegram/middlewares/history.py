from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject

from app.application.services import history as history_service
from app.application.services import spam as spam_service
from app.presentation.telegram.logger import logger
from app.presentation.telegram.utils import other

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class HistoryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: AsyncSession = data["db"]
        if isinstance(event, types.Update) and isinstance(event.message, types.Message):
            message = event.message
            user = message.from_user

            if isinstance(user, types.User):
                try:
                    await history_service.merge_user(db, user)
                except Exception as err:
                    logger.error(f"Error while saving user: {err}")

            try:
                await history_service.save_message(db, message)
            except Exception as err:
                logger.error(f"Error while saving message: {err}")

            if await spam_service.detect_spam(db, message):
                answer = await event.message.answer("🚧 Is spam message?🤔")
                other.sleep_and_delete(answer, 15)

        return await handler(event, data)
