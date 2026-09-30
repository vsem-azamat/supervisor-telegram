"""What the owner is told, and what it costs when it fails.

The catalog is empty and the fan-out question — who among the helpers hears
about a request — cannot be answered from data that does not exist. This is
the part that can be built now: the first profile and the first request are
noticed without anybody reading the database. See docs/architecture.md.
"""

from typing import cast

import pytest
from aiogram import Bot
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.api.deps import current_notifier
from students_cz.services.notify import Notifier

from .conftest import app_for, auth_header

pytestmark = pytest.mark.asyncio


class Watching(Notifier):
    """A notifier that records the pings instead of sending them."""

    def __init__(self) -> None:
        super().__init__(None)
        self.pings: list[str] = []

    async def tell_owner(self, text: str) -> bool:
        self.pings.append(text)
        return True


class BrokenTelegram:
    """A bot whose send blows up, which `notify.tell` is supposed to absorb."""

    async def send_message(self, **kwargs):
        raise RuntimeError("Telegram is having a moment")


async def _client(session: AsyncSession, notifier: Notifier) -> AsyncClient:
    app = app_for(session)
    app.dependency_overrides[current_notifier] = lambda: notifier
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_posted_request_is_reported(session: AsyncSession) -> None:
    watcher = Watching()

    async with await _client(session, watcher) as http:
        response = await http.post(
            "/api/v1/requests",
            json={"text": "нужен матан на ČVUT к 14 февраля"},
            headers=auth_header(94101),
        )

    assert response.status_code == 201
    assert len(watcher.pings) == 1
    # The person's own words, and what the parse made of them — by slug and
    # code, which no language owns. A translated name here would land inside a
    # sentence written in another language.
    assert "нужен матан" in watcher.pings[0]
    assert "matematicka-analyza" in watcher.pings[0]
    assert "cvut" in watcher.pings[0].lower()


async def test_a_published_profile_is_reported_once(session: AsyncSession) -> None:
    """Once, on the way out of draft. Editing a price is not news."""
    watcher = Watching()
    profile = {
        "raw_intro": "Веду матан на ČVUT, 500 Kč в час",
        "publish": True,
    }

    async with await _client(session, watcher) as http:
        first = await http.put("/api/v1/helper", json=profile, headers=auth_header(94102))
        second = await http.put(
            "/api/v1/helper", json=profile, headers=auth_header(94102)
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(watcher.pings) == 1


async def test_a_profile_that_stays_a_draft_is_not_reported(
    session: AsyncSession,
) -> None:
    watcher = Watching()

    async with await _client(session, watcher) as http:
        response = await http.put(
            "/api/v1/helper",
            json={"raw_intro": "ещё думаю", "publish": False},
            headers=auth_header(94103),
        )

    assert response.status_code == 200
    assert watcher.pings == []


async def test_a_ping_that_fails_does_not_fail_the_request(
    session: AsyncSession,
) -> None:
    """The request is committed before anything is sent. It stays committed.

    A real notifier over a bot that raises, not a double that refuses to send:
    the guarantee being tested is `notify.tell` swallowing whatever Telegram
    does, and a double would be testing the double.
    """
    notifier = Notifier(cast(Bot, BrokenTelegram()), None, owner_tg_id=777)

    async with await _client(session, notifier) as http:
        response = await http.post(
            "/api/v1/requests",
            json={"text": "нужна нострификация аттестата"},
            headers=auth_header(94104),
        )

    assert response.status_code == 201


async def test_an_empty_owner_id_is_nobody_rather_than_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the compose file passes when the variable is unset.

    Docker writes `OWNER_TG_ID=` into the environment either way, and an empty
    string is not an integer — so without this the API would refuse to start
    in exactly the configuration that is supposed to mean "no ping".
    """
    from students_cz.core.config import Settings

    # Through the environment, which is the path that breaks: a keyword goes by
    # field name and would be ignored as an unknown extra.
    monkeypatch.setenv("OWNER_TG_ID", "")
    assert Settings(_env_file=None).owner_tg_id is None

    monkeypatch.setenv("OWNER_TG_ID", "777")
    assert Settings(_env_file=None).owner_tg_id == 777


async def test_hiding_and_listing_again_is_not_a_new_profile(
    session: AsyncSession,
) -> None:
    """The same profile coming back, and the owner was told about it once."""
    watcher = Watching()

    async with await _client(session, watcher) as http:
        await http.put(
            "/api/v1/helper",
            json={"raw_intro": "веду матан", "publish": True},
            headers=auth_header(94105),
        )
        await http.put(
            "/api/v1/helper", json={"publish": False}, headers=auth_header(94105)
        )
        await http.put(
            "/api/v1/helper", json={"publish": True}, headers=auth_header(94105)
        )

    assert len(watcher.pings) == 1


async def test_a_request_nobody_could_parse_says_so(session: AsyncSession) -> None:
    """The interesting case: the catalog has no word for what somebody wants."""
    watcher = Watching()

    async with await _client(session, watcher) as http:
        await http.post(
            "/api/v1/requests",
            json={"text": "ыфва цукен"},
            headers=auth_header(94106),
        )

    assert "ничего не разобрали" in watcher.pings[0]


async def test_the_profile_ping_names_what_the_person_offers(
    session: AsyncSession,
) -> None:
    watcher = Watching()

    async with await _client(session, watcher) as http:
        await http.put(
            "/api/v1/helper",
            json={"raw_intro": "веду матан", "publish": True},
            headers=auth_header(94107),
        )
        with_offer = await http.put(
            "/api/v1/helper",
            json={"publish": True, "offers": [{"service_type_id": 1}]},
            headers=auth_header(94108),
        )

    assert with_offer.status_code == 200
    assert "без услуг" in watcher.pings[0]
    assert "без услуг" not in watcher.pings[1]


async def test_a_withdrawn_offer_is_not_named(session: AsyncSession) -> None:
    """`is_active` is what every other query on this table respects.

    Nothing deactivates an offer today — the cabinet deletes what it drops —
    but the column exists and the ping has no business being the one query
    that ignores it.
    """
    from sqlalchemy import select

    from students_cz.db.models import Offer, User

    watcher = Watching()

    async with await _client(session, watcher) as http:
        await http.put(
            "/api/v1/helper",
            json={"publish": False, "offers": [{"service_type_id": 1}]},
            headers=auth_header(94109),
        )
        # This person's own row: the database is seeded, and somebody else's
        # tutoring offer would be the one found by service type alone.
        mine = await session.scalar(select(User).where(User.tg_id == 94109))
        assert mine is not None
        offer = await session.scalar(select(Offer).where(Offer.helper_id == mine.id))
        assert offer is not None
        offer.is_active = False
        await session.flush()

        await http.put(
            "/api/v1/helper", json={"publish": True}, headers=auth_header(94109)
        )

    assert "без услуг" in watcher.pings[0]
