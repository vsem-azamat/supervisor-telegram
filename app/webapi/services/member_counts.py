"""How many people are in a chat, as last recorded.

Read from `chat_member_snapshots` rather than asked of Telegram. This process
has no Telethon client and no session file — the account lives in the bot
container — so every count the console showed came back `None` and rendered as
a dash. The bot writes a snapshot per chat per hour; that row is the answer.

An hour stale is the trade, and it is the right one: a count that costs an API
call per chat per page load would be rate-limited long before it was fresher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.db.models import ChatMemberSnapshot

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


async def latest_for(session: AsyncSession, chat_ids: Iterable[int]) -> dict[int, int]:
    """The newest snapshot per chat, for as many chats as you ask about.

    One query however long the list — the chats list asks about forty-five at
    once, and forty-five round trips to answer one column would be the reason
    the page felt slow.

    Chats with no snapshot are absent from the result rather than present as
    zero. "Not measured" and "empty" are different claims, and the caller has
    to be able to tell them apart.
    """
    ids = list(chat_ids)
    if not ids:
        return {}

    newest = (
        select(
            ChatMemberSnapshot.chat_id,
            func.max(ChatMemberSnapshot.captured_at).label("captured_at"),
        )
        .where(ChatMemberSnapshot.chat_id.in_(ids))
        .group_by(ChatMemberSnapshot.chat_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(ChatMemberSnapshot.chat_id, ChatMemberSnapshot.member_count).join(
                newest,
                (newest.c.chat_id == ChatMemberSnapshot.chat_id)
                & (newest.c.captured_at == ChatMemberSnapshot.captured_at),
            )
        )
    ).all()
    return {row.chat_id: row.member_count for row in rows}


async def latest(session: AsyncSession, chat_id: int) -> int | None:
    """The newest snapshot for one chat, or None if it has never been measured."""
    return (await latest_for(session, [chat_id])).get(chat_id)
