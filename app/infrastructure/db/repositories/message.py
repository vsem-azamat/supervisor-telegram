from datetime import datetime, timedelta
from typing import Any

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

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount or 0

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

    # Statistics methods for webapp
    async def get_message_count_24h(self, chat_id: int) -> int:
        """Get count of messages in chat within last 24 hours."""
        since = datetime.now() - timedelta(hours=24)

        query = select(func.count(Message.id)).where(
            and_(
                Message.chat_id == chat_id,
                Message.timestamp >= since,
                ~Message.spam,  # Exclude spam messages
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_active_users_24h(self, chat_id: int) -> int:
        """Get count of unique active users in chat within last 24 hours."""
        since = datetime.now() - timedelta(hours=24)

        query = select(func.count(func.distinct(Message.user_id))).where(
            and_(
                Message.chat_id == chat_id,
                Message.timestamp >= since,
                ~Message.spam,  # Exclude spam messages
            )
        )

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_last_activity(self, chat_id: int) -> datetime | None:
        """Get timestamp of last message in chat."""
        query = select(Message.timestamp).where(Message.chat_id == chat_id).order_by(Message.timestamp.desc()).limit(1)

        result = await self.db.execute(query)
        return result.scalar()

    async def get_chat_stats_bulk(self, chat_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Get statistics for multiple chats efficiently."""
        since_24h = datetime.now() - timedelta(hours=24)

        # Get message counts for last 24h
        message_counts_query = (
            select(Message.chat_id, func.count(Message.id).label("message_count"))
            .where(and_(Message.chat_id.in_(chat_ids), Message.timestamp >= since_24h, ~Message.spam))
            .group_by(Message.chat_id)
        )

        # Get active user counts for last 24h
        active_users_query = (
            select(Message.chat_id, func.count(func.distinct(Message.user_id)).label("active_users"))
            .where(and_(Message.chat_id.in_(chat_ids), Message.timestamp >= since_24h, ~Message.spam))
            .group_by(Message.chat_id)
        )

        # Get last activity for each chat
        last_activity_query = (
            select(Message.chat_id, func.max(Message.timestamp).label("last_activity"))
            .where(Message.chat_id.in_(chat_ids))
            .group_by(Message.chat_id)
        )

        # Execute queries
        message_counts_result = await self.db.execute(message_counts_query)
        active_users_result = await self.db.execute(active_users_query)
        last_activity_result = await self.db.execute(last_activity_query)

        # Build results dict
        stats: dict[int, dict[str, Any]] = {}

        # Initialize all chats with zero values
        for chat_id in chat_ids:
            stats[chat_id] = {"message_count_24h": 0, "active_users_24h": 0, "last_activity": None}

        # Fill in message counts
        for row in message_counts_result:
            stats[row.chat_id]["message_count_24h"] = row.message_count

        # Fill in active user counts
        for row in active_users_result:
            stats[row.chat_id]["active_users_24h"] = row.active_users

        # Fill in last activity
        for row_data in last_activity_result:
            if row_data.last_activity is not None:
                stats[row_data.chat_id]["last_activity"] = row_data.last_activity

        return stats


def get_message_repository(db: AsyncSession) -> IMessageRepository:
    return MessageRepository(db)
