"""Remembering people, and knowing who may be written to.

The reason this matters is not analytics. Someone who presses start, reads the
description and closes Telegram is invisible to the mini app and is exactly the
person a future announcement is for — so the bot has to record them, and the
record has to say whether writing to them is still allowed.
"""

from datetime import UTC, datetime

import pytest

from students_cz.db.models import User, UserEvent
from students_cz.db.models.enums import UiLang, UserEventKind
from students_cz.services.people import mark_unreachable, reachable, remember

pytestmark = pytest.mark.asyncio

LANGS = ("ru", "cs", "en", "uk")


async def test_the_audience_is_only_people_we_may_write_to(session):
    from sqlalchemy import select

    started = await remember(
        session,
        tg_id=700010,
        first_name="Started",
        supported_langs=LANGS,
        may_write=True,
    )
    never = await remember(
        session,
        tg_id=700011,
        first_name="Never",
        supported_langs=LANGS,
    )
    blocked = await remember(
        session,
        tg_id=700012,
        first_name="Blocked",
        supported_langs=LANGS,
        may_write=True,
    )
    left = await remember(
        session,
        tg_id=700013,
        first_name="Left",
        supported_langs=LANGS,
        may_write=True,
    )
    await session.flush()

    await mark_unreachable(session, 700012, reason="test")
    left.unsubscribed_at = datetime.now(UTC)
    await session.flush()

    audience = set((await session.scalars(reachable().with_only_columns(User.id))).all())
    assert started.id in audience
    assert never.id not in audience, "never let the bot write — Telegram forbids it"
    assert blocked.id not in audience, "Telegram already told us they blocked us"
    assert left.id not in audience, "they asked us to stop"

    # And filtering the audience narrows it rather than widening it.
    by_source = select(User.id).where(User.id.in_(audience))
    assert set((await session.scalars(by_source)).all()) == audience


async def test_being_blocked_is_recorded_once(session):
    from sqlalchemy import func, select

    user = await remember(
        session, tg_id=700020, first_name="B", supported_langs=LANGS, may_write=True
    )
    await session.flush()

    await mark_unreachable(session, 700020, reason="forbidden")
    await mark_unreachable(session, 700020, reason="forbidden")
    await session.flush()

    events = await session.scalar(
        select(func.count(UserEvent.id)).where(
            UserEvent.user_id == user.id, UserEvent.kind == UserEventKind.BOT_BLOCKED
        )
    )
    assert events == 1, "a second 403 for the same person is not new information"


async def test_opening_the_app_again_makes_someone_reachable_once_more(session):
    """Blocking and unblocking is how people come back: the next visit whose
    initData allows writing clears the old 403."""
    from sqlalchemy import select

    await remember(
        session,
        tg_id=700021,
        first_name="Back",
        supported_langs=LANGS,
        may_write=True,
    )
    await session.flush()
    await mark_unreachable(session, 700021, reason="forbidden")
    await session.flush()

    await remember(
        session, tg_id=700021, first_name="Back", supported_langs=LANGS, may_write=True
    )
    user = await session.scalar(select(User).where(User.tg_id == 700021))
    assert user.bot_can_message is True


async def test_an_unknown_institution_is_named_rather_than_a_foreign_key_error(
    session,
):
    from students_cz.schemas import MeUpdate
    from students_cz.services import errors
    from students_cz.services.people import update_profile

    user = User(tg_id=700030, first_name="Nina", ui_lang=UiLang.RU)
    session.add(user)
    await session.flush()

    with pytest.raises(errors.Invalid):
        await update_profile(session, user, MeUpdate(institution_id=10**9))


async def test_a_field_the_payload_does_not_mention_is_left_alone(session):
    """What the form did not ask about, the save does not answer.

    The same rule as the helper profile: a screen that shows three fields must
    not clear the fourth on its way out.
    """
    from students_cz.schemas import MeUpdate
    from students_cz.services.people import update_profile

    user = User(
        tg_id=700031,
        first_name="Oleg",
        ui_lang=UiLang.RU,
        spoken_langs=["ru", "cs"],
        city="Praha",
    )
    session.add(user)
    await session.flush()

    await update_profile(session, user, MeUpdate(ui_lang=UiLang.CS))

    assert user.ui_lang is UiLang.CS
    assert user.city == "Praha"
    assert user.spoken_langs == ["ru", "cs"]


async def test_a_full_name_is_both_parts_and_falls_back_to_the_id(session):
    """Not the catalog's rule — a card shows a first name and an initial."""
    from students_cz.services.people import full_name

    assert (
        full_name(User(tg_id=1, first_name="Нина", last_name="К", ui_lang=UiLang.RU))
        == "Нина К"
    )
    assert full_name(User(tg_id=2, first_name="Нина", ui_lang=UiLang.RU)) == "Нина"
    # Telegram does not allow this; a fixture can.
    nameless = User(tg_id=3, first_name="", ui_lang=UiLang.RU)
    session.add(nameless)
    await session.flush()
    assert full_name(nameless) == str(nameless.id)
