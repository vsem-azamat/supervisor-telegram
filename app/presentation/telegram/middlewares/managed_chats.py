from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject
from sqlalchemy import select

from app.db.models import Chat
from app.moderation import history_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _group_message(event: TelegramObject) -> types.Message | None:
    if not isinstance(event, types.Update) or not isinstance(event.message, types.Message):
        return None
    if event.message.chat.type not in ["group", "supergroup"]:
        return None
    return event.message


class ManagedChatsMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: AsyncSession = data["db"]
        message = _group_message(event)
        if message is not None:
            await history_service.merge_chat(db, message.chat)
            status = await db.scalar(select(Chat.resource_status).where(Chat.id == message.chat.id))
            data["chat_resource_status"] = status or Chat.STATUS_DISCOVERED
            data["chat_is_approved"] = status == Chat.STATUS_APPROVED

        return await handler(event, data)


class ApprovedChatGateMiddleware(BaseMiddleware):
    """Stop active bot behavior in discovered or disabled group resources.

    This middleware must run after HistoryMiddleware so passive history capture
    still happens for resources awaiting approval.
    """

    def __init__(self) -> None:
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if _group_message(event) is not None and not data.get("chat_is_approved", False):
            return None
        return await handler(event, data)
