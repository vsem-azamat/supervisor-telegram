import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject

from app.core.config import settings

if TYPE_CHECKING:
    from app.infrastructure.db.repositories import AdminRepository


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
        if isinstance(event, types.Message) and event.from_user.id in settings.admin.super_admins:
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
        admin_repo: AdminRepository = data["admin_repo"]
        admins_id = [admin.id for admin in await admin_repo.get_db_admins()]
        all_admins_id = admins_id + settings.admin.super_admins
        if isinstance(event, types.Message) and event.from_user.id in all_admins_id:
            return await handler(event, data)
        await you_are_not_admin(event)
        return None  # Stop further handler processing if not Admin
