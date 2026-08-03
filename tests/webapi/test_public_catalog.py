"""The catalogue a stranger sees.

Two things are being pinned here. What gets in — approved, and carrying a link,
with neither condition sufficient alone. And what comes back for each row, which
is four fields: a page cannot leak a Telegram id or a member count that the
response never contained.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.core.time import utc_now
from app.db.models import Chat, Message
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

FIT = -1001370017010
CVUT = -1001405134944
PRIVATE = -1001277626739


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    orig_admins = list(settings.admin.super_admins)
    settings.admin.super_admins = [1]
    from app.webapi.deps import require_super_admin

    app.dependency_overrides.pop(require_super_admin, None)
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.admin.super_admins = orig_admins


def _chat(chat_id: int, title: str, **kwargs) -> Chat:
    chat = Chat(id=chat_id, title=title, resource_status=kwargs.pop("status", Chat.STATUS_APPROVED))
    for key, value in kwargs.items():
        setattr(chat, key, value)
    return chat


async def _seed(session_maker, *chats: Chat) -> None:
    async with session_maker() as session:
        for chat in chats:
            session.add(chat)
        await session.commit()


async def _messages(session_maker, chat_id: int, count: int, *, days_ago: int = 1) -> None:
    when = utc_now() - datetime.timedelta(days=days_ago)
    async with session_maker() as session:
        for n in range(count):
            message = Message(chat_id=chat_id, user_id=7, message_id=n + 1, message="hi")
            # `timestamp` defaults to now and the constructor does not take it,
            # so age has to be set after construction.
            message.timestamp = when
            session.add(message)
        await session.commit()


class TestWhatGetsIn:
    async def test_an_approved_chat_with_a_link_is_listed(self, client_factory, db_session_maker) -> None:
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))

        async with client_factory() as client:
            resp = await client.get("/api/public/catalog")

        assert resp.status_code == 200
        assert [row["title"] for row in resp.json()] == ["ČVUT FIT"]

    async def test_a_chat_without_a_link_stays_out(self, client_factory, db_session_maker) -> None:
        """The link is the decision to publish. No link, no decision, no listing."""
        await _seed(db_session_maker, _chat(PRIVATE, "MUNI: Právnická fakulta"))

        async with client_factory() as client:
            resp = await client.get("/api/public/catalog")

        assert resp.json() == []

    @pytest.mark.parametrize("status", [Chat.STATUS_DISCOVERED, Chat.STATUS_DISABLED])
    async def test_a_link_alone_is_not_enough(self, client_factory, db_session_maker, status: str) -> None:
        """A chat the bot does not moderate is not one to send strangers to."""
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", status=status, public_link="https://t.me/cvut_fit"))

        async with client_factory() as client:
            resp = await client.get("/api/public/catalog")

        assert resp.json() == []


class TestWhatComesBack:
    async def test_the_row_carries_four_fields_and_no_more(self, client_factory, db_session_maker) -> None:
        """Whatever a page does with this, it cannot show what is not here."""
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))

        async with client_factory() as client:
            resp = await client.get("/api/public/catalog")

        assert set(resp.json()[0]) == {"title", "link", "group", "activity"}

    async def test_the_university_above_it_is_named(self, client_factory, db_session_maker) -> None:
        await _seed(
            db_session_maker,
            _chat(CVUT, "ČVUT | ЧВУТ", public_link="https://t.me/cvut_chat"),
            _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit", parent_chat_id=CVUT),
        )

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        by_title = {row["title"]: row for row in rows}
        assert by_title["ČVUT FIT"]["group"] == "ČVUT | ЧВУТ"
        assert by_title["ČVUT | ЧВУТ"]["group"] is None

    async def test_grouped_chats_come_before_ungrouped_ones(self, client_factory, db_session_maker) -> None:
        """The page renders the order it is given rather than sorting again."""
        await _seed(
            db_session_maker,
            _chat(CVUT, "ČVUT | ЧВУТ", public_link="https://t.me/cvut_chat"),
            _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit", parent_chat_id=CVUT),
        )

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        assert [row["title"] for row in rows] == ["ČVUT FIT", "ČVUT | ЧВУТ"]


class TestActivity:
    async def test_a_silent_chat_says_so(self, client_factory, db_session_maker) -> None:
        """Joining a room where nobody has spoken since March should be a choice."""
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        assert rows[0]["activity"] == "quiet"

    async def test_a_handful_of_messages_reads_as_active(self, client_factory, db_session_maker) -> None:
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))
        await _messages(db_session_maker, FIT, 5)

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        assert rows[0]["activity"] == "active"

    async def test_a_hundred_messages_reads_as_busy(self, client_factory, db_session_maker) -> None:
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))
        await _messages(db_session_maker, FIT, 100)

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        assert rows[0]["activity"] == "busy"

    async def test_old_traffic_does_not_keep_a_dead_chat_alive(self, client_factory, db_session_maker) -> None:
        """A chat busy last spring and silent since is silent."""
        await _seed(db_session_maker, _chat(FIT, "ČVUT FIT", public_link="https://t.me/cvut_fit"))
        await _messages(db_session_maker, FIT, 200, days_ago=90)

        async with client_factory() as client:
            rows = (await client.get("/api/public/catalog")).json()

        assert rows[0]["activity"] == "quiet"


async def test_public_catalog_does_not_open_admin_routes(client_factory) -> None:
    async with client_factory() as client:
        catalog = await client.get("/api/public/catalog")
        me = await client.get("/api/auth/me")
        admin_chats = await client.get("/api/chats")

    assert catalog.status_code == 200
    assert me.status_code == 401
    assert admin_chats.status_code == 401
