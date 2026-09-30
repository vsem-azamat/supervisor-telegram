"""Remembering who showed up, and whether we may write to them.

One place for it. The mini app is the only door this process has: `/start`
belongs to the moderator bot, so whether we may write to somebody comes from
the `allows_write_to_pm` flag in their initData. See docs/architecture.md.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.db.models import Institution, User, UserEvent
from students_cz.db.models.enums import UiLang, UserEventKind
from students_cz.schemas import MeUpdate
from students_cz.services.refs import require_row

# Telegram sends a language tag that may carry a region ("en-US"), and may name
# a language we do not ship.
DEFAULT_UI_LANG = UiLang.RU


def pick_ui_lang(language_code: str | None, supported: tuple[str, ...]) -> UiLang:
    if language_code:
        primary = language_code.split("-", 1)[0].lower()
        if primary in supported:
            return UiLang(primary)
    return DEFAULT_UI_LANG


async def remember(
    session: AsyncSession,
    *,
    tg_id: int,
    first_name: str,
    supported_langs: tuple[str, ...],
    last_name: str | None = None,
    username: str | None = None,
    language_code: str | None = None,
    photo_url: str | None = None,
    is_premium: bool = False,
    source: str | None = None,
    may_write: bool = False,
) -> User:
    """Insert or refresh a person, and return them.

    ON CONFLICT rather than find-then-insert: the mini app opens by firing
    several requests at once, each on its own session, and all of them see no
    user. The first insert wins and the rest read the winner's row.
    """
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "tg_id": tg_id,
        "first_name": first_name,
        "last_name": last_name,
        "tg_username": username,
        "photo_url": photo_url,
        "is_premium": is_premium,
        "ui_lang": pick_ui_lang(language_code, supported_langs),
        "last_seen_at": now,
    }
    if source:
        values["source"] = source[:64]
    if may_write:
        # Telegram says the bot may message them. That is also how someone
        # comes back after blocking: the next visit clears the old 403.
        values["bot_started_at"] = now
        values["bot_can_message"] = True

    # Name, username and avatar belong to Telegram and change outside our
    # reach; a stale username breaks the "write to them" link. Everything the
    # person chose here — language, city, whether they unsubscribed — is left
    # alone, and bot_started_at only ever gets set here, never cleared.
    on_update: dict[str, Any] = {
        "first_name": values["first_name"],
        "last_name": values["last_name"],
        "tg_username": values["tg_username"],
        "photo_url": values["photo_url"],
        "is_premium": values["is_premium"],
        "last_seen_at": now,
    }
    if may_write:
        on_update["bot_started_at"] = func.coalesce(User.bot_started_at, now)
        on_update["bot_can_message"] = True

    stmt = (
        pg_insert(User)
        .values(**values)
        .on_conflict_do_update(index_elements=[User.tg_id], set_=on_update)
        .returning(User)
    )
    user = (await session.execute(stmt)).scalar_one()

    # Attribution is about where someone came from, so it is written once and
    # never overwritten by a later link.
    if source and user.source is None:
        user.source = source[:64]

    return user


async def log_event(
    session: AsyncSession,
    user_id: int | None,
    kind: UserEventKind,
    **payload: Any,
) -> None:
    """Record something that happened.

    Never the source of truth for anything: dropping this table must cost
    nothing but hindsight.
    """
    session.add(
        UserEvent(
            user_id=user_id,
            kind=kind,
            payload={k: v for k, v in payload.items() if v is not None},
        )
    )


async def mark_unreachable(session: AsyncSession, tg_id: int, reason: str) -> None:
    """Telegram said we may not write to this person any more.

    A 403 is an answer, not a failure to retry. Recorded so the next
    announcement does not spend a request finding out again.
    """
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None or not user.bot_can_message:
        return
    user.bot_can_message = False
    await log_event(session, user.id, UserEventKind.BOT_BLOCKED, reason=reason)


def reachable(*, langs: list[str] | None = None, source: str | None = None):
    """Everyone an announcement may legitimately go to.

    Three conditions, and all three matter: their initData said the bot may
    write to them (so Telegram permits it), Telegram has not since told us
    otherwise, and they have not asked us to stop.
    """
    stmt = select(User).where(
        User.bot_started_at.is_not(None),
        User.bot_can_message.is_(True),
        User.unsubscribed_at.is_(None),
        User.is_blocked.is_(False),
    )
    if langs:
        stmt = stmt.where(User.ui_lang.in_(langs))
    if source:
        stmt = stmt.where(User.source == source)
    return stmt


async def update_profile(session: AsyncSession, user: User, spec: MeUpdate) -> None:
    """Apply what the account screen sent, and nothing it did not send.

    A field the payload leaves out — or leaves null — is a question the screen
    did not ask, so it is not an answer to overwrite with. `institution_id: 0`
    is the one exception and means "no school": it is how the picker says
    cleared, since a null cannot be told from an omission here.

    The institution is checked before it is written so an id nobody has ever
    seen answers as the field it is, rather than as a foreign-key violation
    from Postgres.
    """
    if spec.ui_lang is not None:
        user.ui_lang = spec.ui_lang
    if spec.spoken_langs is not None:
        user.spoken_langs = spec.spoken_langs
    if spec.city is not None:
        user.city = spec.city or None
    if spec.institution_id is not None:
        await require_row(
            session, Institution, spec.institution_id or None, "institution_id"
        )
        user.institution_id = spec.institution_id or None


def full_name(user: User) -> str:
    """Someone's name as they gave it to Telegram.

    Three screens want this and each had written it out: your own account, the
    name beside an answer to your request, and the owner ping. Not the same
    rule as a catalog card, which shows a first name and an initial — full
    surnames are neither needed to choose somebody nor ours to publish. This
    one is used where the reader is either the person themselves or somebody
    already talking to them.

    The id is the fallback for a row with no first name, which Telegram does
    not allow and a seeded fixture might.
    """
    return " ".join(filter(None, (user.first_name, user.last_name))) or str(user.id)
