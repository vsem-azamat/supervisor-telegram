from aiogram import Router, types
from aiogram.filters import Command

from app.infrastructure.db.repositories import AdminRepository
from app.presentation.telegram.utils import other

admin_router = Router()


@admin_router.message(Command("admin", prefix="!/"))
async def new_admin(message: types.Message, admin_repo: AdminRepository) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Используйте эту команду в ответ на сообщение пользователя.")
        return
    target_user = message.reply_to_message.from_user
    if not await admin_repo.is_admin(target_user.id):
        await admin_repo.insert_admin(target_user.id)
        await message.answer(f"Админ {other.get_user_mention(target_user)} добавлен ✅")
    else:
        await message.answer(f"Админ {other.get_user_mention(target_user)} уже есть в базе.")
    await message.delete()


@admin_router.message(Command("unadmin", prefix="!/"))
async def delete_admin(message: types.Message, admin_repo: AdminRepository) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Используйте эту команду в ответ на сообщение пользователя.")
        return
    target_user = message.reply_to_message.from_user
    if await admin_repo.is_admin(target_user.id):
        await admin_repo.delete_admin(target_user.id)
        await message.answer(f"Админ {other.get_user_mention(target_user)} удален ❌")
    else:
        await message.answer(f"Админ {other.get_user_mention(target_user)} не является админом.")
    await message.delete()
