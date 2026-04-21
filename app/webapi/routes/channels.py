"""Channels — list and detail endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, ChannelPost, ChannelSource
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import ChannelDetail, ChannelRead, ChannelSourceRead, PostRead

router = APIRouter(prefix="/channels", tags=["channels"])

_RECENT_POSTS_PER_CHANNEL = 10


@router.get("", response_model=list[ChannelRead])
async def list_channels(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[Channel]:
    result = await session.execute(select(Channel).order_by(Channel.name))
    return list(result.scalars().all())


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelDetail:
    channel = (await session.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    sources_rows = (
        (
            await session.execute(
                select(ChannelSource)
                .where(ChannelSource.channel_id == channel.telegram_id)
                .order_by(ChannelSource.enabled.desc(), ChannelSource.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    posts_rows = (
        (
            await session.execute(
                select(ChannelPost)
                .where(ChannelPost.channel_id == channel.telegram_id)
                .order_by(ChannelPost.created_at.desc())
                .limit(_RECENT_POSTS_PER_CHANNEL)
            )
        )
        .scalars()
        .all()
    )

    return ChannelDetail(
        **ChannelRead.model_validate(channel).model_dump(),
        review_chat_id=channel.review_chat_id,
        posting_schedule=channel.posting_schedule,
        publish_schedule=channel.publish_schedule,
        footer_template=channel.footer_template,
        discovery_query=channel.discovery_query,
        modified_at=channel.modified_at,
        sources=[ChannelSourceRead.model_validate(s) for s in sources_rows],
        recent_posts=[PostRead.model_validate(p) for p in posts_rows],
    )
