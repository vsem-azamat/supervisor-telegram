"""Channel posts — list + detail endpoints for the review panel."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChannelPost
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import PostDetail, PostRead

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[PostRead])
async def list_posts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    status: str | None = Query(default=None, description="Filter by PostStatus"),
    channel_id: int | None = Query(default=None, description="Filter by Channel.telegram_id"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChannelPost]:
    stmt = select(ChannelPost).order_by(ChannelPost.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ChannelPost.status == status)
    if channel_id is not None:
        stmt = stmt.where(ChannelPost.channel_id == channel_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChannelPost:
    result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    return post
