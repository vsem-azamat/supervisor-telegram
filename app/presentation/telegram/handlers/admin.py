"""!admin / !unadmin — trusting somebody with the chat the command was sent in.

The chat is not an argument because it should not be one. Whoever is handing out
moderator rights is standing in the room they are handing them out for, and a
command that could name any of forty-five chats from anywhere is a command that
grants the wrong one eventually.
"""

from aiogram import Router, types
from aiogram.filters import Command

from app.core.logging import get_logger
from app.db.repositories import AdminRepository
from app.presentation.telegram.utils import other

logger = get_logger("handlers.admin")
admin_router = Router()

_REPLY_REQUIRED = "Используйте эту команду в ответ на сообщение пользователя."


@admin_router.message(Command("admin", prefix="!/"))
async def new_admin(message: types.Message, admin_repo: AdminRepository) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer(_REPLY_REQUIRED)
        return

    target_user = message.reply_to_message.from_user
    granted_by = message.from_user.id if message.from_user else None
    mention = other.get_user_mention(target_user)

    if await admin_repo.grant(target_user.id, message.chat.id, granted_by=granted_by):
        chats = await admin_repo.chats_for(target_user.id)
        suffix = f" Всего чатов под модерацией: {len(chats)}." if len(chats) > 1 else ""
        await message.answer(f"{mention} — модератор этого чата ✅{suffix}")
        logger.info("admin_granted", user_id=target_user.id, chat_id=message.chat.id, by=granted_by)
    else:
        await message.answer(f"{mention} уже модерирует этот чат.")

    await message.delete()


@admin_router.message(Command("unadmin", prefix="!/"))
async def delete_admin(message: types.Message, admin_repo: AdminRepository) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer(_REPLY_REQUIRED)
        return

    target_user = message.reply_to_message.from_user
    mention = other.get_user_mention(target_user)

    if await admin_repo.revoke(target_user.id, message.chat.id):
        chats = await admin_repo.chats_for(target_user.id)
        suffix = f" Остаётся модератором ещё в {len(chats)} чатах." if chats else ""
        await message.answer(f"{mention} больше не модерирует этот чат ❌{suffix}")
        logger.info("admin_revoked", user_id=target_user.id, chat_id=message.chat.id)
    else:
        await message.answer(f"{mention} и так не модерирует этот чат.")

    await message.delete()
