from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import ChatEntity
from app.infrastructure.db.models import Chat
from app.domain.repositories import IChatRepository


class ChatRepository(IChatRepository):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, chat_id: int) -> ChatEntity | None:
        """Get chat by ID."""
        result = await self.db.execute(select(Chat).filter(Chat.id == chat_id))
        chat_model = result.scalars().first()
        if not chat_model:
            return None
        return self._model_to_entity(chat_model)

    async def get_all(self) -> list[ChatEntity]:
        """Get all chats."""
        result = await self.db.execute(select(Chat))
        chat_models = result.scalars().all()
        return [self._model_to_entity(chat_model) for chat_model in chat_models]

    async def exists(self, chat_id: int) -> bool:
        """Check if chat exists."""
        result = await self.db.execute(select(Chat.id).filter(Chat.id == chat_id))
        return result.scalars().first() is not None

    async def save(self, chat: ChatEntity) -> ChatEntity:
        """Save chat."""
        chat_model = await self._get_chat_model(chat.id)
        if chat_model:
            chat_model.title = chat.title
            chat_model.is_forum = chat.is_forum
            chat_model.welcome_message = chat.welcome_message
            chat_model.time_delete = chat.welcome_delete_time
            chat_model.is_welcome_enabled = chat.is_welcome_enabled
            chat_model.is_captcha_enabled = chat.is_captcha_enabled
        else:
            chat_model = Chat(
                id=chat.id,
                title=chat.title,
                is_forum=chat.is_forum,
                welcome_message=chat.welcome_message,
                time_delete=chat.welcome_delete_time,
                is_welcome_enabled=chat.is_welcome_enabled,
                is_captcha_enabled=chat.is_captcha_enabled,
            )
            self.db.add(chat_model)

        await self.db.commit()
        await self.db.refresh(chat_model)
        return self._model_to_entity(chat_model)

    async def _get_chat_model(self, chat_id: int) -> Chat | None:
        """Get chat model by ID."""
        result = await self.db.execute(select(Chat).filter(Chat.id == chat_id))
        return result.scalars().first()

    def _model_to_entity(self, chat_model: Chat) -> ChatEntity:
        """Convert chat model to entity."""
        return ChatEntity(
            id=chat_model.id,
            title=chat_model.title,
            is_forum=chat_model.is_forum,
            welcome_message=chat_model.welcome_message,
            welcome_delete_time=chat_model.time_delete,
            is_welcome_enabled=chat_model.is_welcome_enabled,
            is_captcha_enabled=chat_model.is_captcha_enabled,
            created_at=chat_model.created_at,
            modified_at=chat_model.modified_at,
        )

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
