from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import ChatLinkEntity
from app.domain.repositories import IChatLinkRepository
from app.infrastructure.db.models import ChatLink


class ChatLinkRepository(IChatLinkRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self) -> list[ChatLinkEntity]:
        """Get all chat links ordered by priority."""
        result = await self.db.execute(select(ChatLink).order_by(ChatLink.priority.desc()))
        chat_links = result.scalars().all()
        return [self._model_to_entity(link) for link in chat_links]

    async def save(self, chat_link: ChatLinkEntity) -> ChatLinkEntity:
        """Save chat link."""
        if chat_link.id:
            # Update existing
            existing = await self.db.get(ChatLink, chat_link.id)
            if existing:
                existing.text = chat_link.text
                existing.link = chat_link.link
                existing.priority = chat_link.priority
            else:
                raise ValueError(f"ChatLink with id {chat_link.id} not found")
        else:
            # Create new
            new_link = ChatLink(text=chat_link.text, link=chat_link.link, priority=chat_link.priority)
            self.db.add(new_link)

        await self.db.commit()

        if chat_link.id and existing:
            await self.db.refresh(existing)
            return self._model_to_entity(existing)
        await self.db.refresh(new_link)
        return self._model_to_entity(new_link)

    async def delete(self, link_id: int) -> None:
        """Delete chat link."""
        await self.db.execute(delete(ChatLink).where(ChatLink.id == link_id))
        await self.db.commit()

    def _model_to_entity(self, chat_link_model: ChatLink) -> ChatLinkEntity:
        """Convert database model to domain entity."""
        return ChatLinkEntity(
            id=chat_link_model.id,
            text=chat_link_model.text,
            link=chat_link_model.link,
            priority=chat_link_model.priority,
        )

    # Legacy method for backward compatibility
    async def get_chat_links(self) -> Sequence[ChatLink]:
        result = await self.db.execute(select(ChatLink).order_by(ChatLink.priority.desc()))
        return result.scalars().all()


def get_chat_link_repository(db: AsyncSession) -> IChatLinkRepository:
    return ChatLinkRepository(db)
