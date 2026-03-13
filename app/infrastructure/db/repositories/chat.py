from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Chat


class ChatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, chat_id: int) -> Chat | None:
        """Get chat by ID."""
        result = await self.db.execute(select(Chat).filter(Chat.id == chat_id))
        return result.scalars().first()

    async def get_all(self) -> list[Chat]:
        """Get all chats."""
        result = await self.db.execute(select(Chat))
        return list(result.scalars().all())

    async def exists(self, chat_id: int) -> bool:
        """Check if chat exists."""
        result = await self.db.execute(select(Chat.id).filter(Chat.id == chat_id))
        return result.scalars().first() is not None

    async def save(self, chat: Chat) -> Chat:
        """Save chat."""
        chat_model = await self._get_chat_model(chat.id)
        if chat_model:
            chat_model.title = chat.title
            chat_model.is_forum = chat.is_forum
            chat_model.welcome_message = chat.welcome_message
            chat_model.time_delete = chat.time_delete
            chat_model.is_welcome_enabled = chat.is_welcome_enabled
            chat_model.is_captcha_enabled = chat.is_captcha_enabled
        else:
            chat_model = Chat(
                id=chat.id,
                title=chat.title,
                is_forum=chat.is_forum,
                welcome_message=chat.welcome_message,
                time_delete=chat.time_delete,
                is_welcome_enabled=chat.is_welcome_enabled,
                is_captcha_enabled=chat.is_captcha_enabled,
            )
            self.db.add(chat_model)

        await self.db.commit()
        await self.db.refresh(chat_model)
        return chat_model

    async def _get_chat_model(self, chat_id: int) -> Chat | None:
        """Get chat model by ID."""
        result = await self.db.execute(select(Chat).filter(Chat.id == chat_id))
        return result.scalars().first()

    # Legacy methods for backward compatibility
    async def get_chat(self, id_tg_chat: int) -> Chat | None:
        """Get chat model by ID."""
        return await self._get_chat_model(id_tg_chat)

    async def get_chats(self) -> list[Chat]:
        """Get all chats as models."""
        result = await self.db.execute(select(Chat))
        return list(result.scalars().all())

    async def merge_chat(
        self,
        id_tg_chat: int,
        title: str | None = None,
        is_forum: bool | None = None,
    ) -> None:
        """Merge chat information."""
        chat_model = await self._get_chat_model(id_tg_chat)
        if chat_model:
            if title is not None:
                chat_model.title = title
            if is_forum is not None:
                chat_model.is_forum = is_forum
        else:
            chat_model = Chat(
                id=id_tg_chat,
                title=title,
                is_forum=is_forum or False,
            )
            self.db.add(chat_model)

        await self.db.commit()

    async def update_welcome_message(self, id_tg_chat: int, message: str) -> None:
        """Update welcome message."""
        await self.db.execute(update(Chat).filter(Chat.id == id_tg_chat).values(welcome_message=message))
        await self.db.commit()


def get_chat_repository(db: AsyncSession) -> ChatRepository:
    return ChatRepository(db)
