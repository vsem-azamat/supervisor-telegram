"""What the ad detector caught, as the console reads it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import Chat, SpamPing, User
from app.webapi.schemas import SpamPingRead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def read_pings(session: AsyncSession, *, chat_id: int | None, limit: int) -> list[SpamPingRead]:
    """Ad-detector hits, newest first, with the chat's title and the author.

    Chats and users the bot never stored come back without a title or a name;
    an author with no row cannot be on the blacklist either.
    """
    stmt = (
        select(SpamPing, Chat.title, User)
        .join(Chat, Chat.id == SpamPing.chat_id, isouter=True)
        .join(User, User.id == SpamPing.user_id, isouter=True)
        .order_by(SpamPing.detected_at.desc())
        .limit(limit)
    )
    if chat_id is not None:
        stmt = stmt.where(SpamPing.chat_id == chat_id)

    rows = (await session.execute(stmt)).all()
    return [
        SpamPingRead(
            id=ping.id,
            chat_id=ping.chat_id,
            chat_title=title,
            user_id=ping.user_id,
            username=user.username if user else None,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            blocked=bool(user and user.blocked),
            message_id=ping.message_id,
            kind=ping.kind,
            matches=ping.matches,
            snippet=ping.snippet,
            detected_at=ping.detected_at,
        )
        for ping, title, user in rows
    ]
