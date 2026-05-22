"""Persistence for ad_leads — the rate-card funnel tracking rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.time import utc_now
from app.db.models import AdLead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AdLeadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, lead_id: int) -> AdLead | None:
        result = await self.db.execute(select(AdLead).where(AdLead.id == lead_id))
        return result.scalars().first()

    async def create_lead(self, *, chat_id: int, user_id: int, snippet: str | None) -> AdLead:
        lead = AdLead(chat_id=chat_id, user_id=user_id, snippet=snippet)
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def set_reached_via(self, lead_id: int, reached_via: str) -> None:
        await self.set_outreach_result(lead_id, reached_via)

    async def set_outreach_result(
        self,
        lead_id: int,
        reached_via: str,
        *,
        ping_chat_id: int | None = None,
        ping_message_id: int | None = None,
    ) -> None:
        lead = await self.get_by_id(lead_id)
        if lead is None:
            return
        lead.reached_via = reached_via
        lead.ping_chat_id = ping_chat_id
        lead.ping_message_id = ping_message_id
        await self.db.commit()

    async def clear_ping_message(self, lead_id: int) -> None:
        lead = await self.get_by_id(lead_id)
        if lead is None:
            return
        lead.ping_chat_id = None
        lead.ping_message_id = None
        await self.db.commit()

    async def mark_clicked(self, lead_id: int) -> bool:
        """Stamp link_clicked_at if not already set. Returns True if a lead was found."""
        lead = await self.get_by_id(lead_id)
        if lead is None:
            return False
        if lead.link_clicked_at is None:
            lead.link_clicked_at = utc_now()
            await self.db.commit()
        return True
