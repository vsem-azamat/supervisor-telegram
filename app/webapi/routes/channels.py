"""Channels — list, detail, and mutation endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel import channel_repo, source_manager
from app.db.models import Channel, ChannelPost, ChannelSource
from app.db.session import create_session_maker
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import (
    ChannelCreate,
    ChannelDetail,
    ChannelMutationResponse,
    ChannelRead,
    ChannelSourceCreate,
    ChannelSourceRead,
    ChannelSourceUpdate,
    ChannelUpdate,
    PostRead,
)

router = APIRouter(prefix="/channels", tags=["channels"])

_RECENT_POSTS_PER_CHANNEL = 10


@router.get("", response_model=list[ChannelRead])
async def list_channels(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[Channel]:
    result = await session.execute(select(Channel).order_by(Channel.name))
    return list(result.scalars().all())


@router.post("", response_model=ChannelDetail, status_code=201)
async def create_channel(
    payload: ChannelCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelDetail:
    try:
        channel = await channel_repo.create_channel(
            create_session_maker(),
            telegram_id=payload.telegram_id,
            name=payload.name,
            description=payload.description,
            language=payload.language,
            username=payload.username,
            review_chat_id=payload.review_chat_id,
            max_posts_per_day=payload.max_posts_per_day,
            posting_schedule=payload.posting_schedule,
            discovery_query=payload.discovery_query,
            source_discovery_query=payload.source_discovery_query,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=f"Channel with telegram_id {payload.telegram_id} already exists"
        ) from err
    session.expire_all()
    return await _load_detail(session, channel.id)


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelDetail:
    return await _load_detail(session, channel_id)


@router.patch("/{channel_id}", response_model=ChannelDetail)
async def update_channel(
    channel_id: int,
    payload: ChannelUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelDetail:
    channel = (await session.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await _load_detail(session, channel_id)
    updated = await channel_repo.update_channel(create_session_maker(), channel.telegram_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    # Repo wrote via its own session; drop request-session's identity map so
    # the follow-up SELECT in _load_detail sees the new values.
    session.expire_all()
    return await _load_detail(session, channel_id)


@router.delete("/{channel_id}", response_model=ChannelMutationResponse)
async def delete_channel(
    channel_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelMutationResponse:
    channel = (await session.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    deleted = await channel_repo.delete_channel(create_session_maker(), channel.telegram_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    return ChannelMutationResponse(channel_id=channel_id, message=f"Channel '{channel.name}' deleted.")


@router.post("/{channel_id}/sources", response_model=ChannelSourceRead, status_code=201)
async def add_source(
    channel_id: int,
    payload: ChannelSourceCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelSource:
    channel = (await session.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    added = await source_manager.add_source(
        create_session_maker(),
        channel_id=channel.telegram_id,
        url=payload.url,
        title=payload.title,
        added_by="webui",
    )
    if not added:
        raise HTTPException(status_code=409, detail="Source URL already exists for this channel")
    return (
        await session.execute(
            select(ChannelSource).where(
                ChannelSource.channel_id == channel.telegram_id, ChannelSource.url == payload.url
            )
        )
    ).scalar_one()


@router.patch("/{channel_id}/sources/{source_id}", response_model=ChannelSourceRead)
async def update_source(
    channel_id: int,
    source_id: int,
    payload: ChannelSourceUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelSource:
    src = (
        await session.execute(
            select(ChannelSource)
            .join(Channel, Channel.telegram_id == ChannelSource.channel_id)
            .where(ChannelSource.id == source_id, Channel.id == channel_id)
        )
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Source not found")
    src.enabled = payload.enabled
    await session.commit()
    await session.refresh(src)
    return src


@router.delete("/{channel_id}/sources/{source_id}", response_model=ChannelMutationResponse)
async def delete_source(
    channel_id: int,
    source_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelMutationResponse:
    src = (
        await session.execute(
            select(ChannelSource)
            .join(Channel, Channel.telegram_id == ChannelSource.channel_id)
            .where(ChannelSource.id == source_id, Channel.id == channel_id)
        )
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await session.delete(src)
    await session.commit()
    return ChannelMutationResponse(channel_id=channel_id, message="Source removed.")


async def _load_detail(session: AsyncSession, channel_id: int) -> ChannelDetail:
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
