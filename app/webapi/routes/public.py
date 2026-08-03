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
from app.db.models import Chat, Message
from app.webapi.deps import get_session
from app.webapi.schemas import PublicCatalogItem

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
