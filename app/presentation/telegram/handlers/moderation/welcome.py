"""!welcome command — set per-chat welcome message."""

from aiogram import Router, types
from aiogram.filters import Command

from app.db.repositories import ChatRepository

router = Router()


@router.message(Command("welcome", prefix="!/"))
async def welcome_change(message: types.Message, chat_repo: ChatRepository) -> None:
    if not message.text:
        await message.answer("Сообщение не может быть пустым.")
        return
    welcome_message = message.text.partition(" ")[2]
    await chat_repo.update_welcome_message(message.chat.id, welcome_message)
    await message.answer("<b>Приветственное сообщение изменено!</b>")
    await message.answer(welcome_message)
    await message.delete()
