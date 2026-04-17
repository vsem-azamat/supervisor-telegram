from aiogram import types
from aiogram.filters import BaseFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories import get_admin_repository


class SuperAdminFilter(BaseFilter):
    async def __call__(self, msg: types.Message) -> bool:
        if not msg.from_user:
            return False
        return msg.from_user.id in settings.admin.super_admins


class AdminFilter(BaseFilter):
    async def __call__(self, msg: types.Message, db: AsyncSession) -> bool:
        if not msg.from_user:
            return False
        admin_repo = get_admin_repository(db)
        admins_id = [admin.id for admin in await admin_repo.get_db_admins()]
        return msg.from_user.id in admins_id


class ChatTypeFilter(BaseFilter):
    def __init__(self, chat_type: str | list[str]):
        self.chat_type = chat_type

    async def __call__(self, message: types.Message) -> bool:
        if isinstance(self.chat_type, str):
            return message.chat.type == self.chat_type
        return message.chat.type in self.chat_type
