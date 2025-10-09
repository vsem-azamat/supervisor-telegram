from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject

from app.application.services import history as history_service
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
        spam_detector = data.get("spam_service")
        if isinstance(event, types.Update) and isinstance(event.message, types.Message):
            message = event.message
            user = message.from_user

            if isinstance(user, types.User):
                try:
                    await history_service.merge_user(db, user)
                except Exception as err:
                    logger.error(f"Error while saving user: {err}")

            spam_detected = False
            if spam_detector and isinstance(user, types.User):
                try:
                    spam_detected = await spam_detector.detect(
                        chat_id=message.chat.id,
                        user_id=user.id,
                        text=message.text or message.caption,
                    )
                except Exception as err:
                    logger.error(f"Error during spam detection: {err}")

            try:
                await history_service.save_message(db, message)
            except Exception as err:
                logger.error(f"Error while saving message: {err}")

            if spam_detected:
                answer = await event.message.answer("🚧 Is spam message?🤔")
                await other.sleep_and_delete(answer, 15)

        return await handler(event, data)
