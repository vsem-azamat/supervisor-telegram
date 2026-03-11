import asyncio

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.db.repositories import (
    ChatRepository,
    MessageRepository,
    UserRepository,
)

logger = get_logger("moderation")


async def add_to_blacklist(
    db: AsyncSession,
    bot: Bot,
    id_tg: int,
    revoke_messages: bool | None = None,
) -> None:
    user_repo = UserRepository(db)
    chat_repo = ChatRepository(db)
    message_repo = MessageRepository(db)
    await user_repo.add_to_blacklist(id_tg)

    async def ban_user(chat_id: int) -> None:
        try:
            try:
                await bot.ban_chat_member(chat_id, id_tg, revoke_messages=revoke_messages)
            except Exception as err:
                logger.warning(f"Failed to ban user {id_tg} in chat {chat_id}.\nError: {err}")

            if revoke_messages:
                user_messages = await message_repo.get_user_messages(id_tg)
                for message in user_messages:
                    try:
                        await bot.delete_message(
                            chat_id=message.chat_id,
                            message_id=message.message_id,
                        )
                    except Exception as err:
                        logger.warning(
                            f"Failed to delete message {message.message_id} in chat {chat_id}.\nError: {err}"
                        )

        except Exception as err:
            logger.warning(
                f"Failed to ban user {id_tg} in chat {chat_id}.\n"
                f"Maybe the user is already banned or not in the chat.\n"
                f"Error: {err}"
            )

    tasks = [ban_user(chat.id) for chat in await chat_repo.get_chats()]
    await asyncio.gather(*tasks)


async def remove_from_blacklist(db: AsyncSession, bot: Bot, id_tg: int) -> None:
    user_repo = UserRepository(db)
    chat_repo = ChatRepository(db)

    await user_repo.remove_from_blacklist(id_tg)

    async def unban_user(chat_id: int) -> None:
        try:
            await bot.unban_chat_member(chat_id, id_tg)
        except Exception as err:
            logger.warning(f"Failed to unban user {id_tg} in chat {chat_id}.\nError: {err}")

    tasks = [unban_user(chat.id) for chat in await chat_repo.get_chats()]
    await asyncio.gather(*tasks)
