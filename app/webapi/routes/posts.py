"""Channel posts — list + detail endpoints for the review panel."""

from __future__ import annotations

from typing import Annotated

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.generator import GeneratedPost
from app.channel.publisher import publish_post as _publish_to_channel
from app.channel.review.image_tools import (
    ImageToolsDeps,
    add_image_url_op,
    clear_images_op,
    find_and_add_image_op,
    remove_image_op,
    reorder_images_op,
    use_candidate_op,
)
from app.channel.review.service import (
    approve_post,
    regen_post_text,
    reject_post,
    set_post_text,
)
from app.core.config import settings
from app.db.models import Channel, ChannelPost
from app.db.session import create_session_maker
from app.webapi.deps import get_publish_bot, get_session, require_super_admin
from app.webapi.schemas import (
    ImageAddUrlRequest,
    ImageMutationResponse,
    ImageReorderRequest,
    ImageSearchRequest,
    ImageUseRequest,
    PostDetail,
    PostMutationResponse,
    PostRead,
    PostTextEdit,
)

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


@router.post("/{post_id}/regenerate", response_model=PostMutationResponse)
async def regenerate(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> PostMutationResponse:
    """Re-run the generator over the post's stored source_items and replace the body.

    Looks up the channel to resolve language + footer; falls back to defaults
    when the channel row is missing (e.g. test fixtures).
    """
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

    ch = (await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))).scalar_one_or_none()
    language = ch.language if ch else "ru"
    footer = ch.footer if ch else ""

    msg, _ = await regen_post_text(
        post_id=post_id,
        api_key=settings.openrouter.api_key,
        model=settings.channel.generation_model,
        language=language,
        session_maker=create_session_maker(),
        footer=footer,
    )
    session.expire_all()
    await session.refresh(post)
    return PostMutationResponse(post_id=post_id, status=post.status, message=msg)


# ---------------------------------------------------------------------------
# Image pool endpoints
# ---------------------------------------------------------------------------


def _image_deps(post: ChannelPost) -> ImageToolsDeps:
    return ImageToolsDeps(
        session_maker=create_session_maker(),
        post_id=post.id,
        channel_id=post.channel_id,
        api_key=settings.openrouter.api_key,
        vision_model=settings.channel.vision_model,
        brave_api_key=settings.brave.api_key,
    )


def _build_image_response(post: ChannelPost, message: str) -> ImageMutationResponse:
    return ImageMutationResponse(
        post_id=post.id,
        message=message,
        image_urls=list(post.image_urls or []),
        image_candidates=list(post.image_candidates or []),
    )


async def _load_post_or_404(session: AsyncSession, post_id: int) -> ChannelPost:
    post = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
    return post


@router.post("/{post_id}/images/use", response_model=ImageMutationResponse)
async def image_use(
    post_id: int,
    payload: ImageUseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await use_candidate_op(_image_deps(post), payload.pool_index, payload.position)
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)


@router.post("/{post_id}/images/url", response_model=ImageMutationResponse)
async def image_add_url(
    post_id: int,
    payload: ImageAddUrlRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await add_image_url_op(_image_deps(post), payload.url, payload.position)
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)


@router.post("/{post_id}/images/search", response_model=ImageMutationResponse)
async def image_search(
    post_id: int,
    payload: ImageSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await find_and_add_image_op(_image_deps(post), payload.query)
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)


@router.delete("/{post_id}/images/{position}", response_model=ImageMutationResponse)
async def image_remove(
    post_id: int,
    position: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await remove_image_op(_image_deps(post), position)
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)


@router.post("/{post_id}/images/reorder", response_model=ImageMutationResponse)
async def image_reorder(
    post_id: int,
    payload: ImageReorderRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await reorder_images_op(_image_deps(post), payload.order)
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)


@router.delete("/{post_id}/images", response_model=ImageMutationResponse)
async def image_clear(
    post_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ImageMutationResponse:
    post = await _load_post_or_404(session, post_id)
    msg = await clear_images_op(_image_deps(post))
    session.expire_all()
    await session.refresh(post)
    return _build_image_response(post, msg)
