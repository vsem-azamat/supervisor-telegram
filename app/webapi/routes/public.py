"""Public read-only endpoints.

Keep this router intentionally narrow. Public pages should consume explicit
safe projections from here instead of reusing admin DTOs by accident.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, ChatLink
from app.webapi.deps import get_session
from app.webapi.schemas import PublicCatalogItem

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/catalog", response_model=list[PublicCatalogItem])
async def get_public_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PublicCatalogItem]:
    """Return only the fields that are safe to show without admin auth."""
    chat_links = (
        (await session.execute(select(ChatLink).order_by(ChatLink.priority.desc(), ChatLink.text))).scalars().all()
    )
    channels = (
        (await session.execute(select(Channel).where(Channel.enabled.is_(True)).order_by(Channel.name))).scalars().all()
    )

    rows = [
        *[
            PublicCatalogItem(
                resource_type="chat",
                id=chat_link.id,
                title=chat_link.text,
                subtitle=chat_link.link,
            )
            for chat_link in chat_links
        ],
        *[
            PublicCatalogItem(
                resource_type="channel",
                id=channel.id,
                title=channel.name,
                subtitle=f"@{channel.username}" if channel.username else None,
            )
            for channel in channels
        ],
    ]
    return sorted(rows, key=lambda row: (row.title.lower(), row.resource_type, row.id))
