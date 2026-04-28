"""Mechanical setup-gap detection — surfaces suggestion cards on the dashboard.

Each rule is a self-contained handler that returns ``list[SuggestionItem]``.
The router runs them sequentially against a single session, then concatenates
the results. New rules just need a new handler + an entry in ``_RULES``.

These rules are deliberately mechanical (pure SQL on existing tables) — no LLM
calls, no Telethon RPCs. The dashboard can poll this freely.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Channel, ChannelSource, Chat, Message
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import SuggestionItem, SuggestionsResponse

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

# Per-rule cap so a misconfigured deployment doesn't drown the dashboard
# in cards. Total upper bound = len(_RULES) * _PER_RULE_CAP.
_PER_RULE_CAP = 3
_SILENT_DAYS = 14
_UNMODERATED_GRACE_DAYS = 7


def _label_chat(chat_id: int, title: str | None) -> str:
    return title or f"#{chat_id}"


# ---------------------------------------------------------------------------
# Rule handlers
# ---------------------------------------------------------------------------


async def _rule_disabled_channels(session: AsyncSession) -> list[SuggestionItem]:
    rows = (
        await session.execute(
            select(Channel.id, Channel.name)
            .where(Channel.enabled.is_(False))
            .order_by(Channel.modified_at.desc())
            .limit(_PER_RULE_CAP)
        )
    ).all()
    return [
        SuggestionItem(
            kind="disabled_channel",
            severity="info",
            title=f"Disabled channel: {name}",
            hint="Re-enable to resume the content pipeline, or delete if it's retired.",
            target_id=cid,
            target_label=name,
            action_url=f"/channels/{cid}",
            action_label="Open",
        )
        for cid, name in rows
    ]


async def _rule_channels_without_sources(session: AsyncSession) -> list[SuggestionItem]:
    rows = (
        await session.execute(
            select(Channel.id, Channel.name)
            .where(Channel.enabled.is_(True))
            .where(~exists().where(ChannelSource.channel_id == Channel.id))
            .order_by(Channel.created_at.desc())
            .limit(_PER_RULE_CAP)
        )
    ).all()
    return [
        SuggestionItem(
            kind="channel_without_sources",
            severity="warning",
            title=f"No sources: {name}",
            hint="Add an RSS feed or run discovery — the pipeline can't generate posts otherwise.",
            target_id=cid,
            target_label=name,
            action_url=f"/channels/{cid}",
            action_label="Configure",
        )
        for cid, name in rows
    ]


async def _rule_channels_without_username(session: AsyncSession) -> list[SuggestionItem]:
    """A managed Telegram channel without a public @handle is still publishable
    but breaks footer rendering and link sharing — flag so admins can fill it in."""
    rows = (
        await session.execute(
            select(Channel.id, Channel.name)
            .where(Channel.enabled.is_(True))
            .where(Channel.username.is_(None))
            .where(Channel.telegram_id.is_not(None))
            .order_by(Channel.created_at.desc())
            .limit(_PER_RULE_CAP)
        )
    ).all()
    return [
        SuggestionItem(
            kind="channel_without_username",
            severity="info",
            title=f"No @username: {name}",
            hint="Set the public handle so footer and share links resolve.",
            target_id=cid,
            target_label=name,
            action_url=f"/channels/{cid}",
            action_label="Set username",
        )
        for cid, name in rows
    ]


async def _rule_unmoderated_chats(session: AsyncSession, now: datetime.datetime) -> list[SuggestionItem]:
    """Top-level chats with both welcome and captcha disabled, that have been
    around long enough that "we just added it" is no longer a defence."""
    cutoff = now - datetime.timedelta(days=_UNMODERATED_GRACE_DAYS)
    rows = (
        await session.execute(
            select(Chat.id, Chat.title)
            .where(Chat.parent_chat_id.is_(None))
            .where(Chat.is_welcome_enabled.is_(False))
            .where(Chat.is_captcha_enabled.is_(False))
            .where(Chat.modified_at < cutoff)
            .order_by(Chat.modified_at.desc())
            .limit(_PER_RULE_CAP)
        )
    ).all()
    return [
        SuggestionItem(
            kind="unmoderated_chat",
            severity="warning",
            title=f"No welcome/captcha: {_label_chat(cid, title)}",
            hint="No welcome or captcha — new joiners aren't filtered.",
            target_id=cid,
            target_label=_label_chat(cid, title),
            action_url=f"/chats/{cid}",
            action_label="Configure",
        )
        for cid, title in rows
    ]


async def _rule_silent_chats(session: AsyncSession, now: datetime.datetime) -> list[SuggestionItem]:
    """Chats with zero recorded messages over the lookback window — likely
    abandoned/archived. The created_at filter avoids flagging fresh additions."""
    cutoff = now - datetime.timedelta(days=_SILENT_DAYS)
    rows = (
        await session.execute(
            select(Chat.id, Chat.title)
            .where(Chat.created_at < cutoff)
            .where(~exists().where((Message.chat_id == Chat.id) & (Message.timestamp >= cutoff)))
            .order_by(Chat.created_at.asc())
            .limit(_PER_RULE_CAP)
        )
    ).all()
    return [
        SuggestionItem(
            kind="silent_chat",
            severity="info",
            title=f"Silent {_SILENT_DAYS}d: {_label_chat(cid, title)}",
            hint="No messages recorded in the last fortnight. Archive or revisit.",
            target_id=cid,
            target_label=_label_chat(cid, title),
            action_url=f"/chats/{cid}",
            action_label="Open",
        )
        for cid, title in rows
    ]


async def _rule_orphan_chats(session: AsyncSession) -> list[SuggestionItem]:
    """Chats neither parented nor parenting any other chat — fully isolated nodes.

    Only surfaces when there are at least two such chats — a single isolated
    chat can be a deliberate solo, but two+ unconnected ones usually means
    the admin forgot to wire up the network."""
    parented_subq = select(Chat.parent_chat_id).where(Chat.parent_chat_id.is_not(None)).distinct().subquery()
    rows = (
        await session.execute(
            select(Chat.id, Chat.title)
            .where(Chat.parent_chat_id.is_(None))
            .where(~Chat.id.in_(select(parented_subq.c.parent_chat_id)))
            .order_by(Chat.created_at.desc())
            .limit(_PER_RULE_CAP + 1)
        )
    ).all()
    if len(rows) < 2:
        return []
    return [
        SuggestionItem(
            kind="orphan_chat",
            severity="info",
            title=f"Orphan: {_label_chat(cid, title)}",
            hint="Not connected to any network. Set a parent or attach children.",
            target_id=cid,
            target_label=_label_chat(cid, title),
            action_url=f"/chats/{cid}",
            action_label="Set parent",
        )
        for cid, title in rows[:_PER_RULE_CAP]
    ]


async def _rule_networks_without_channel(session: AsyncSession) -> list[SuggestionItem]:
    """For every chat-tree (multi-node clusters via parent_chat_id), check
    whether any managed channel has its review_chat_id pointing into the tree.

    Single-node "trees" don't qualify — those are covered by the orphan rule.
    Skipped entirely if no channels exist (empty deployment)."""
    has_channels = (await session.execute(select(exists().select_from(Channel)))).scalar()
    if not has_channels:
        return []

    chats = (await session.execute(select(Chat.id, Chat.title, Chat.parent_chat_id))).all()
    if not chats:
        return []

    # Build parent → list[child] map and id → (title, parent) lookup.
    children_of: dict[int, list[int]] = {}
    chat_meta: dict[int, tuple[str | None, int | None]] = {}
    for cid, title, parent in chats:
        chat_meta[cid] = (title, parent)
        if parent is not None:
            children_of.setdefault(parent, []).append(cid)

    review_targets = {
        row[0]
        for row in (
            await session.execute(select(Channel.review_chat_id).where(Channel.review_chat_id.is_not(None)))
        ).all()
    }

    suggestions: list[SuggestionItem] = []
    for cid, (title, parent) in chat_meta.items():
        if parent is not None:
            continue  # not a root
        # Walk descendants
        tree: set[int] = {cid}
        stack = [cid]
        while stack:
            node = stack.pop()
            for child in children_of.get(node, ()):
                if child not in tree:
                    tree.add(child)
                    stack.append(child)
        if len(tree) < 2:
            continue  # single-node, covered by orphan rule
        if tree & review_targets:
            continue  # at least one channel points into this network
        label = _label_chat(cid, title)
        suggestions.append(
            SuggestionItem(
                kind="network_without_channel",
                severity="attention",
                title=f"No channel: {label}",
                hint=f"Network has {len(tree)} chats but no managed channel. Create one to publish posts.",
                target_id=cid,
                target_label=label,
                action_url="/channels",
                action_label="Create channel",
            )
        )
        if len(suggestions) >= _PER_RULE_CAP:
            break
    return suggestions


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


@router.get("", response_model=SuggestionsResponse)
async def list_suggestions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SuggestionsResponse:
    now = utc_now()
    items: list[SuggestionItem] = []
    items.extend(await _rule_networks_without_channel(session))
    items.extend(await _rule_disabled_channels(session))
    items.extend(await _rule_channels_without_sources(session))
    items.extend(await _rule_channels_without_username(session))
    items.extend(await _rule_unmoderated_chats(session, now))
    items.extend(await _rule_silent_chats(session, now))
    items.extend(await _rule_orphan_chats(session))
    return SuggestionsResponse(items=items, generated_at=now)
