import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject

from app.core.config import settings

if TYPE_CHECKING:
    from app.infrastructure.db.repositories import AdminRepository

# TTL cache for admin user IDs (same pattern as BlacklistMiddleware)
_admin_cache: tuple[set[int], float] | None = None
_CACHE_TTL = 300  # 5 minutes


def invalidate_admin_cache() -> None:
    """Invalidate the admin cache so next check re-fetches from DB."""
    global _admin_cache  # noqa: PLW0603
    _admin_cache = None


async def you_are_not_admin(event: TelegramObject, text: str = "🚫 You are not an Admin.") -> None:
    """Inform user that they are not an admin and remove helper messages."""
    if isinstance(event, types.Message):
        answer = await event.answer(text)
        await event.delete()
        await asyncio.sleep(5)
        await answer.delete()


class SuperAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, (types.Message, types.CallbackQuery))
            and event.from_user
            and event.from_user.id in settings.admin.super_admins
        ):
            return await handler(event, data)
        await you_are_not_admin(event, "You are not a Super Admin.")
        return None  # Stop further handler processing if not SuperAdmin


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        global _admin_cache  # noqa: PLW0603

        admin_repo: AdminRepository = data["admin_repo"]

        now = time.monotonic()
        if _admin_cache is not None and _admin_cache[1] > now:
            admin_ids = _admin_cache[0]
        else:
            db_admins = await admin_repo.get_db_admins()
            admin_ids = {admin.id for admin in db_admins}
            _admin_cache = (admin_ids, now + _CACHE_TTL)

        all_admins_id = admin_ids | set(settings.admin.super_admins)
        if (
            isinstance(event, (types.Message, types.CallbackQuery))
            and event.from_user
            and event.from_user.id in all_admins_id
        ):
            return await handler(event, data)
        await you_are_not_admin(event)
        return None  # Stop further handler processing if not Admin
