from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import and_

from app.domain.entities import MessageEntity
from app.domain.repositories import IMessageRepository
from app.infrastructure.db.models import Message


class MessageRepository(IMessageRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(self, message: MessageEntity) -> MessageEntity:
        """Save message entity."""
        # Check if message exists
        existing_query = select(Message).where(
            and_(
                Message.chat_id == message.chat_id,
                Message.user_id == message.user_id,
                Message.message_id == message.message_id,
            )
        )
        result = await self.db.execute(existing_query)
        existing = result.scalars().first()

        if existing:
            # Update existing
            existing.message = message.content
            existing.message_info = message.metadata or {}
            existing.spam = message.is_spam
        else:
            # Create new
            new_message = Message(
                chat_id=message.chat_id,
                user_id=message.user_id,
                message_id=message.message_id,
                message=message.content,
                message_info=message.metadata or {},
                spam=message.is_spam,
            )
            self.db.add(new_message)

        await self.db.commit()

        # Return updated entity
        return message

    async def add_message(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        message: str | None,
        message_info: dict,
    ) -> None:
        await self.db.execute(
            insert(Message).values(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                message=message,
                message_info=message_info,
            )
        )
        await self.db.commit()

    async def label_spam(self, chat_id: int, message_id: int) -> None:
        query = (
            update(Message).where(and_(Message.chat_id == chat_id, Message.message_id == message_id)).values(spam=True)
        )
        await self.db.execute(query)
        await self.db.commit()

    async def get_user_messages(self, user_id: int, chat_id: int | None = None) -> list[MessageEntity]:
        """Get messages by user, optionally filtered by chat."""
        query = select(Message).where(Message.user_id == user_id)
        if chat_id is not None:
            query = query.where(Message.chat_id == chat_id)

        result = await self.db.execute(query)
        messages = result.scalars().all()
        return [self._model_to_entity(msg) for msg in messages]

    async def get_spam_messages(self, limit: int | None = None) -> list[MessageEntity]:
        """Get spam messages."""
        query = select(Message).where(Message.spam)
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        messages = result.scalars().all()
        return [self._model_to_entity(msg) for msg in messages]

    async def delete_user_messages(self, user_id: int, chat_id: int | None = None) -> int:
        """Delete user messages and return count."""
        query = delete(Message).where(Message.user_id == user_id)
        if chat_id is not None:
            query = query.where(Message.chat_id == chat_id)

        cursor = await self.db.execute(query)
        await self.db.commit()
        return cursor.rowcount or 0  # type: ignore[attr-defined]

    def _model_to_entity(self, message_model: Message) -> MessageEntity:
        """Convert database model to domain entity."""
        return MessageEntity(
            id=message_model.id,
            chat_id=message_model.chat_id,
            user_id=message_model.user_id,
            message_id=message_model.message_id,
            content=message_model.message,
            metadata=message_model.message_info,
            timestamp=message_model.timestamp,
            is_spam=message_model.spam,
        )

    async def count_user_chats(self, user_id: int) -> int:
        query = select(func.count(func.distinct(Message.chat_id))).where(Message.user_id == user_id)
        result = await self.db.execute(query)
        count = result.scalar()
        return count or 0

    async def count_user_messages(self, user_id: int) -> int:
        query = select(func.count()).where(Message.user_id == user_id)
        result = await self.db.execute(query)
        count = result.scalar()
        return count or 0

    async def is_first_message(self, chat_id: int, user_id: int) -> bool:
        query = select(func.count()).where(Message.user_id == user_id, Message.chat_id == chat_id)
        result = await self.db.execute(query)
        count = result.scalar()
        return count is not None and count > 0

    async def is_similar_spam_message(self, message: str) -> bool:
        query = select(func.count()).where(Message.message == message, Message.spam)
        result = await self.db.execute(query)
        count = result.scalar()
        return count is not None and count > 0


def get_message_repository(db: AsyncSession) -> IMessageRepository:
    return MessageRepository(db)
