"""The console has one door: a signed Mini App payload.

The Login Widget and the magic link are gone, so what is pinned here is that
nothing else opens it. A forged signature, a stale one, and a real signature
from somebody who is not a super administrator all fail — and they fail
differently in the log and identically to the caller.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import pytest
from app.core.config import settings
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

BOT_TOKEN = "test:bot:token"  # noqa: S105
SUPER_ADMIN_ID = 268388996


def _init_data(*, user_id: int, token: str = BOT_TOKEN, age_seconds: int = 0, signature: str | None = "Xf2pQ") -> str:
    """Build an initData string the way Telegram would.

    Note the secret: HMAC over the literal b"WebAppData", not sha256 of the
    token. The Login Widget used the other one, and signing this payload that
    way is exactly the forgery the endpoint has to refuse.

    And note `signature`, present by default because Telegram has sent it since
    Bot API 7.10 — there is no current client that omits it. Every test here
    once built the payload without it, so the suite stayed green through eight
    days in which the endpoint refused every genuine sign-in.
    """
    issued = int(datetime.datetime.now(tz=datetime.UTC).timestamp()) - age_seconds
    fields = {
        "auth_date": str(issued),
        "query_id": "AAF",
        "user": json.dumps({"id": user_id, "first_name": "A"}, separators=(",", ":")),
    }
    if signature is not None:
        fields["signature"] = signature
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session, require_super_admin

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    orig_admins = list(settings.admin.super_admins)
    orig_token = settings.telegram.token
    orig_secure = settings.webapi.session_cookie_secure
    settings.admin.super_admins = [SUPER_ADMIN_ID]
    settings.telegram.token = BOT_TOKEN
    settings.webapi.session_cookie_secure = False

    app.dependency_overrides.pop(require_super_admin, None)
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.admin.super_admins = orig_admins
    settings.telegram.token = orig_token
    settings.webapi.session_cookie_secure = orig_secure


async def test_me_unauthenticated_returns_401(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_a_signed_payload_opens_a_session(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.post("/api/auth/webapp", json={"init_data": _init_data(user_id=SUPER_ADMIN_ID)})
        assert resp.status_code == 200, resp.text
        assert resp.cookies.get(settings.webapi.session_cookie_name)

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == SUPER_ADMIN_ID

        out = await client.post("/api/auth/logout")
        assert out.status_code == 204

        after = await client.get("/api/auth/me")
        assert after.status_code == 401


async def test_a_payload_from_a_client_that_predates_the_signature_field_still_opens_a_session(
    client_factory,
) -> None:
    """The field is not required — only covered by the digest when it is there."""
    async with client_factory() as client:
        resp = await client.post(
            "/api/auth/webapp",
            json={"init_data": _init_data(user_id=SUPER_ADMIN_ID, signature=None)},
        )

    assert resp.status_code == 200, resp.text


async def test_a_refused_signature_and_a_refused_admin_are_told_apart(client_factory) -> None:
    """401 is "Telegram did not sign this"; 403 is "signed, but not for you".

    The console shows one screen for both, and it reads as the second. That is
    how a verification bug spent eight days looking like a missing entry in the
    super-admin list.
    """
    async with client_factory() as client:
        unsigned = await client.post("/api/auth/webapp", json={"init_data": "auth_date=1&hash=deadbeef"})
        stranger = await client.post("/api/auth/webapp", json={"init_data": _init_data(user_id=99999)})

    assert unsigned.status_code == 401
    assert stranger.status_code == 403


async def test_a_payload_signed_with_another_token_is_refused(client_factory) -> None:
    """Which is what a Mini App belonging to a different bot would send."""
    forged = _init_data(user_id=SUPER_ADMIN_ID, token="someone:elses:token")  # noqa: S106

    async with client_factory() as client:
        resp = await client.post("/api/auth/webapp", json={"init_data": forged})

    assert resp.status_code == 401
    assert not resp.cookies.get(settings.webapi.session_cookie_name)


async def test_a_stale_payload_is_refused(client_factory) -> None:
    """A signature stays valid forever; replaying one must not."""
    async with client_factory() as client:
        resp = await client.post(
            "/api/auth/webapp",
            json={"init_data": _init_data(user_id=SUPER_ADMIN_ID, age_seconds=90_000)},
        )

    assert resp.status_code == 401


async def test_a_genuine_stranger_is_refused(client_factory) -> None:
    """Telegram vouches for who they are, not for what they may do."""
    async with client_factory() as client:
        resp = await client.post("/api/auth/webapp", json={"init_data": _init_data(user_id=99999)})

    assert resp.status_code == 403
    assert not resp.cookies.get(settings.webapi.session_cookie_name)


async def test_an_empty_payload_is_refused(client_factory) -> None:
    """The case a browser outside Telegram would produce."""
    async with client_factory() as client:
        resp = await client.post("/api/auth/webapp", json={"init_data": ""})

    assert resp.status_code == 401


async def test_the_old_doors_are_gone(client_factory) -> None:
    """Deleting a login route is only true if nothing still answers on it."""
    async with client_factory() as client:
        widget = await client.post("/api/auth/login", json={"id": SUPER_ADMIN_ID, "auth_date": 0, "hash": "x"})
        magic = await client.post("/api/auth/magic-link", json={"token": "x"})

    assert widget.status_code == 404
    assert magic.status_code == 404
