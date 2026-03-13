from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repositories import ChatLinkRepository


async def get_contacts_buttons() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Dev", url="https://t.me/vsem_azamat"),
        InlineKeyboardButton(text="GitHub", url="https://github.com/vsem-azamat/moderator-bot"),
    )
    builder.adjust(1)
    return builder


async def get_chat_buttons(db: AsyncSession) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    chat_links_repo = ChatLinkRepository(db)
    chats = await chat_links_repo.get_chat_links()
    for chat in chats:
        builder.add(InlineKeyboardButton(text=chat.text, url=chat.link))
    builder.adjust(2)
    return builder
