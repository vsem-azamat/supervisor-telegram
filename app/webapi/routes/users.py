"""Users — global blacklist (block / unblock) endpoints.

Block/unblock are global ops that touch every managed chat — they reuse the
existing ``app.moderation.blacklist`` service unchanged. The webapi-owned
``publish_bot`` (Phase 4b) is the outgoing Telegram client.
"""

from __future__ import annotations

from typing import Annotated

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundException
from app.db.models import User
from app.moderation.blacklist import add_to_blacklist, remove_from_blacklist
from app.webapi.deps import get_publish_bot, get_session, require_super_admin
from app.webapi.schemas import UserBlockRequest, UserBlockResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/{user_id}/block", response_model=UserBlockResponse)
async def block_user(
    user_id: int,
    payload: UserBlockRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> UserBlockResponse:
    await add_to_blacklist(session, bot, user_id, revoke_messages=payload.revoke_messages or None)
    return UserBlockResponse(
        user_id=user_id,
        blocked=True,
        message="User blocked across all managed chats." + (" Messages revoked." if payload.revoke_messages else ""),
    )


@router.delete("/{user_id}/block", response_model=UserBlockResponse)
async def unblock_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> UserBlockResponse:
    try:
        await remove_from_blacklist(session, bot, user_id)
    except UserNotFoundException as err:
        raise HTTPException(status_code=404, detail=f"User {user_id} not in DB") from err
    return UserBlockResponse(user_id=user_id, blocked=False, message="User unblocked.")


@router.get("/{user_id}", response_model=UserBlockResponse)
async def get_user_block_status(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> UserBlockResponse:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not in DB")
    return UserBlockResponse(
        user_id=user_id,
        blocked=user.blocked,
        message="blocked" if user.blocked else "not blocked",
    )
