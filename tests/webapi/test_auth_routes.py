"""Auth route coverage."""

from __future__ import annotations

import datetime
import hashlib
import hmac
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _sign(payload: dict[str, str], token: str) -> str:
    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    orig_admins = list(settings.admin.super_admins)
    orig_token = settings.telegram.token
    orig_bypass = settings.webapi.dev_bypass_auth
    orig_secure = settings.webapi.session_cookie_secure
    settings.admin.super_admins = [268388996]
    settings.telegram.token = "test:bot:token"  # noqa: S105
    settings.webapi.dev_bypass_auth = False
    settings.webapi.session_cookie_secure = False
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.admin.super_admins = orig_admins
    settings.telegram.token = orig_token
    settings.webapi.dev_bypass_auth = orig_bypass
    settings.webapi.session_cookie_secure = orig_secure


async def test_me_unauthenticated_returns_401(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_full_login_flow(client_factory) -> None:
    now_s = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    str_payload = {"id": "268388996", "auth_date": str(now_s), "first_name": "A"}
    str_payload["hash"] = _sign(str_payload, "test:bot:token")
    json_payload = {"id": 268388996, "auth_date": now_s, "first_name": "A", "hash": str_payload["hash"]}

    async with client_factory() as client:
        resp = await client.post("/api/auth/login", json=json_payload)
        assert resp.status_code == 200, resp.text
        assert resp.cookies.get(settings.webapi.session_cookie_name)

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == 268388996

        out = await client.post("/api/auth/logout")
        assert out.status_code == 204


async def test_non_admin_rejected(client_factory) -> None:
    now_s = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    str_payload = {"id": "99999", "auth_date": str(now_s)}
    str_payload["hash"] = _sign(str_payload, "test:bot:token")
    json_payload = {"id": 99999, "auth_date": now_s, "hash": str_payload["hash"]}
    async with client_factory() as client:
        resp = await client.post("/api/auth/login", json=json_payload)
    assert resp.status_code == 403
