from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.repositories.chat import ChatRepository
from app.db.repositories.sponsored_ads import SponsoredAdRequestRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import SponsoredAdRequest


class SponsoredAdRequestService:
    def __init__(self, db: AsyncSession) -> None:
        self._chat_repo = ChatRepository(db)
        self._request_repo = SponsoredAdRequestRepository(db)

    async def open_from_flagged_message(
        self,
        *,
        target_chat_id: int,
        advertiser_user_id: int,
        source_message_id: int | None,
        source_message_text: str | None,
    ) -> SponsoredAdRequest:
        chat = await self._chat_repo.get_by_id(target_chat_id)
        if chat is None:
            raise ValueError("chat_not_found")
        if not chat.ad_enabled:
            raise ValueError("ads_disabled_for_chat")

        return await self._request_repo.create_from_flagged_message(
            target_chat_id=target_chat_id,
            advertiser_user_id=advertiser_user_id,
            source_message_id=source_message_id,
            source_message_text=source_message_text,
        )
