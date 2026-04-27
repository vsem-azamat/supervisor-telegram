"""Channel posts — list + detail endpoints for the review panel."""

from __future__ import annotations

from typing import Annotated

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.generator import GeneratedPost
from app.channel.publisher import publish_post as _publish_to_channel
from app.channel.review.service import approve_post, reject_post, set_post_text
from app.db.models import ChannelPost
from app.db.session import create_session_maker
from app.webapi.deps import get_publish_bot, get_session, require_super_admin
from app.webapi.schemas import PostDetail, PostMutationResponse, PostRead, PostTextEdit

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


@router.post("/{post_id}/approve", response_model=PostMutationResponse)
async def approve(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    async def _publish_fn(channel_id: int, gen_post: GeneratedPost) -> int | None:
        return await _publish_to_channel(bot, channel_id, gen_post)

    msg, published_msg_id = await approve_post(
        post_id=post_id,
        channel_id=post.channel_id,
        publish_fn=_publish_fn,
        session_maker=create_session_maker(),
    )
    await session.refresh(post)
    return PostMutationResponse(
        post_id=post_id,
        status=post.status,
        message=msg,
        published_msg_id=published_msg_id,
    )


@router.post("/{post_id}/reject", response_model=PostMutationResponse)
async def reject(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    msg = await reject_post(post_id, create_session_maker())
    await session.refresh(post)
    return PostMutationResponse(post_id=post_id, status=post.status, message=msg)


@router.patch("/{post_id}/text", response_model=PostMutationResponse)
async def edit_text(
    post_id: int,
    payload: PostTextEdit,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    msg = await set_post_text(post_id, payload.text, create_session_maker())
    await session.refresh(post)
    return PostMutationResponse(post_id=post_id, status=post.status, message=msg)
