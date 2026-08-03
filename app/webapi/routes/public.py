"""Public read-only endpoints.

Keep this router intentionally narrow. Public pages should consume explicit
safe projections from here instead of reusing admin DTOs by accident.
"""

from __future__ import annotations

import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot, Message
from app.webapi.deps import get_session
from app.webapi.schemas import PublicCatalogItem, PublicReach, PublicReachGroup

router = APIRouter(prefix="/public", tags=["public"])

# How far back "is this chat alive" looks. A university chat goes quiet over the
# summer and busy in September, so a fortnight would call half the catalogue
# dead every August.
ACTIVITY_WINDOW = datetime.timedelta(days=30)

# Messages in that window. The bands are coarse deliberately: the reader is
# deciding whether a chat is worth joining, not comparing two of them.
BUSY_FROM = 100
ACTIVE_FROM = 10

# Days within the window on which anything at all was recorded, below which the
# window is not evidence about anybody.
#
# The bot was out of these chats between 22 May and 3 August, so on the day it
# returned a thirty-day count held one day of traffic. Every chat that had seen
# a single message read "active", including the one with seven thousand messages
# to its name and the one with two. The count was correct and the claim was
# false, which is the worst combination to ship: nothing looks broken.
#
# So the claim is withheld until there is a fortnight behind it, and it comes
# back on its own. This is a property of the recording, not of any one chat —
# a gap affects all of them at once.
MIN_OBSERVED_DAYS = 14

# Sorts after every real title, so ungrouped chats land at the end rather than
# at the top where an empty string would put them.
_UNGROUPED = "￿"

# What a chat with no university above it is called on the reach table. The
# catalogue page picks the same word for the same rows.
UNGROUPED_LABEL = "Остальные"


def _activity(messages: int, *, grounded: bool) -> Literal["unknown", "quiet", "active", "busy"]:
    if not grounded:
        return "unknown"
    if messages >= BUSY_FROM:
        return "busy"
    if messages >= ACTIVE_FROM:
        return "active"
    return "quiet"


async def _observed_days(session: AsyncSession, since: datetime.datetime) -> int:
    """Days in the window on which the bot recorded anything, anywhere.

    Counted across the whole network rather than per chat: a quiet chat with no
    messages is a fact about the chat, while a quiet *database* is a fact about
    whether the bot was there to listen.
    """
    result = await session.execute(
        select(func.count(func.distinct(func.date(Message.timestamp)))).where(Message.timestamp >= since)
    )
    return result.scalar() or 0


@router.get("/catalog", response_model=list[PublicCatalogItem])
async def get_public_catalog(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PublicCatalogItem]:
    """Every chat a stranger may join, under the university above it.

    A chat is here when it is approved *and* has a public link. The link is the
    decision — there is no separate flag that could disagree with it — so a
    private faculty group without one cannot appear by accident, and taking a
    chat down means clearing one column.
    """
    parent = aliased(Chat)
    since = utc_now() - ACTIVITY_WINDOW
    grounded = await _observed_days(session, since) >= MIN_OBSERVED_DAYS

    recent_messages = (
        select(Message.chat_id, func.count().label("messages"))
        .where(Message.timestamp >= since)
        .group_by(Message.chat_id)
        .subquery()
    )

    rows = (
        await session.execute(
            select(
                Chat.title,
                Chat.public_link,
                parent.title.label("group_title"),
                func.coalesce(recent_messages.c.messages, 0).label("messages"),
            )
            .outerjoin(parent, parent.id == Chat.parent_chat_id)
            .outerjoin(recent_messages, recent_messages.c.chat_id == Chat.id)
            .where(Chat.resource_status == Chat.STATUS_APPROVED)
            .where(Chat.public_link.is_not(None))
        )
    ).all()

    items = [
        PublicCatalogItem(
            title=row.title,
            link=row.public_link,
            group=row.group_title,
            activity=_activity(row.messages, grounded=grounded),
        )
        for row in rows
        if row.title and row.public_link
    ]
    # Grouped and alphabetical, so the page renders what the server already
    # decided instead of sorting forty-five rows again in the browser.
    return sorted(items, key=lambda item: ((item.group or _UNGROUPED).lower(), item.title.lower()))


@router.get("/reach", response_model=PublicReach)
async def get_public_reach(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PublicReach:
    """How far a post across the published catalogue would carry.

    Counted over the same rows `/catalog` returns and no others. Reach summed
    across private chats would be a claim about rooms nobody being quoted a
    price can see, and publishing their size is not ours to do.

    Member counts come from the snapshots the userbot writes, never from
    Telethon at request time: this endpoint answers strangers, and a public URL
    that reaches into the account behind it is a public URL somebody can point
    at the account. The newest snapshot per chat is the answer — the loop writes
    a row per poll, and summing all of them would count the same people once per
    observation.
    """
    newest = (
        select(
            ChatMemberSnapshot.chat_id,
            func.max(ChatMemberSnapshot.captured_at).label("captured_at"),
        )
        .group_by(ChatMemberSnapshot.chat_id)
        .subquery()
    )
    latest = (
        select(ChatMemberSnapshot.chat_id, ChatMemberSnapshot.member_count)
        .join(
            newest,
            (newest.c.chat_id == ChatMemberSnapshot.chat_id) & (newest.c.captured_at == ChatMemberSnapshot.captured_at),
        )
        .subquery()
    )

    parent = aliased(Chat)
    rows = (
        await session.execute(
            select(parent.title.label("group_title"), latest.c.member_count)
            # Explicit, because the first column named here belongs to the
            # aliased parent and the second to a subquery — left to infer it,
            # SQLAlchemy starts the FROM from the wrong one and joins `chats`
            # in twice.
            .select_from(Chat)
            .outerjoin(parent, parent.id == Chat.parent_chat_id)
            .outerjoin(latest, latest.c.chat_id == Chat.id)
            .where(Chat.resource_status == Chat.STATUS_APPROVED)
            .where(Chat.public_link.is_not(None))
        )
    ).all()

    groups: dict[str, PublicReachGroup] = {}
    measured = 0
    for row in rows:
        name = row.group_title or UNGROUPED_LABEL
        group = groups.setdefault(name, PublicReachGroup(name=name, chats=0, members=0))
        group.chats += 1
        if row.member_count is not None:
            group.members += row.member_count
            measured += 1

    return PublicReach(
        chats=len(rows),
        members=sum(group.members for group in groups.values()),
        measured_chats=measured,
        # Largest first: the table is read as "where would this post land",
        # and the answer starts with the biggest room.
        groups=sorted(groups.values(), key=lambda group: (-group.members, group.name.lower())),
    )
