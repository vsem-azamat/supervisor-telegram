import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot, types
from aiogram.types import TelegramObject

from app.application.services import history as history_service
from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# TTL cache for chat admin checks (chat_id -> (admin_ids, expire_time))
_admin_cache: dict[int, tuple[set[int], float]] = {}
_CACHE_TTL = 300  # 5 minutes


async def _is_managed_chat(bot: Bot, chat_id: int) -> bool:
    """Check if bot's super admin is an admin in the chat (cached)."""
    now = time.monotonic()
    cached = _admin_cache.get(chat_id)
    if cached and cached[1] > now:
        admin_ids = cached[0]
    else:
        chat_admins = await bot.get_chat_administrators(chat_id)
        admin_ids = {admin.user.id for admin in chat_admins}
        _admin_cache[chat_id] = (admin_ids, now + _CACHE_TTL)

    return any(sa in admin_ids for sa in settings.admin.super_admins)


class ManagedChatsMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot = data["bot"]
        db: AsyncSession = data["db"]
        if (
            isinstance(event, types.Update)
            and isinstance(event.message, types.Message)
            and event.message.chat.type in ["group", "supergroup"]
        ):
            message = event.message
            if await _is_managed_chat(bot, message.chat.id):
                await history_service.merge_chat(db, message.chat)
                return await handler(event, data)

            # If no super admin in chat, leave
            await bot.leave_chat(message.chat.id)
            # Invalidate cache for this chat
            _admin_cache.pop(message.chat.id, None)
            return None
        return await handler(event, data)
