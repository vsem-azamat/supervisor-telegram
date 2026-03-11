import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot, types
from aiogram.types import TelegramObject

from app.presentation.telegram.logger import logger

if TYPE_CHECKING:
    from app.infrastructure.db.repositories import UserRepository

# TTL cache for blocked user IDs (same pattern as ManagedChatsMiddleware)
_blacklist_cache: tuple[set[int], float] | None = None
_CACHE_TTL = 300  # 5 minutes


def invalidate_blacklist_cache() -> None:
    """Invalidate the blacklist cache so next check re-fetches from DB."""
    global _blacklist_cache  # noqa: PLW0603
    _blacklist_cache = None


class BlacklistMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        global _blacklist_cache  # noqa: PLW0603

        bot: Bot = data["bot"]
        user_repo: UserRepository = data["user_repo"]

        now = time.monotonic()
        if _blacklist_cache is not None and _blacklist_cache[1] > now:
            blacklisted_ids = _blacklist_cache[0]
        else:
            blacklisted_users = await user_repo.get_blocked_users()
            blacklisted_ids = {user.id for user in blacklisted_users}
            _blacklist_cache = (blacklisted_ids, now + _CACHE_TTL)

        if isinstance(event, types.Message) and event.from_user and event.from_user.id in blacklisted_ids:
            try:
                await bot.ban_chat_member(event.chat.id, event.from_user.id)
                await event.delete()
            except Exception as e:
                logger.error(f"Failed to ban or delete message for user {event.from_user.id}: {e}")
            return None  # Stop further handler processing for blacklisted user

        return await handler(event, data)
