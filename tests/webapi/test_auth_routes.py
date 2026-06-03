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
    from app.webapi.routes import auth as auth_routes

    auth_routes._clear_login_bot_username_cache()
    orig_admins = list(settings.admin.super_admins)
    orig_token = settings.telegram.token
    orig_auth_mode = settings.webapi.auth_mode
    orig_login_start_payload = settings.webapi.login_start_payload
    orig_secure = settings.webapi.session_cookie_secure
    settings.admin.super_admins = [268388996]
    settings.telegram.token = "test:bot:token"  # noqa: S105
    settings.webapi.auth_mode = "telegram"
    settings.webapi.login_start_payload = "web_admin_login"
    settings.webapi.session_cookie_secure = False
    from app.webapi.deps import require_super_admin

    app.dependency_overrides.pop(require_super_admin, None)
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.admin.super_admins = orig_admins
    settings.telegram.token = orig_token
    settings.webapi.auth_mode = orig_auth_mode
    settings.webapi.login_start_payload = orig_login_start_payload
    settings.webapi.session_cookie_secure = orig_secure
    auth_routes._clear_login_bot_username_cache()


async def test_me_unauthenticated_returns_401(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_auth_config_returns_current_auth_mode(client_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.webapi.routes import auth as auth_routes

    async def fake_fetch_bot_username() -> str:
        return "dynamic_bot"

    monkeypatch.setattr(auth_routes, "_fetch_login_bot_username", fake_fetch_bot_username)
    settings.webapi.auth_mode = "magic_link"
    settings.webapi.login_start_payload = "admin_login_dev"

    async with client_factory() as client:
        resp = await client.get("/api/auth/config")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "auth_mode": "magic_link",
        "bot_username": "dynamic_bot",
        "bot_start_url": "https://t.me/dynamic_bot?start=admin_login_dev",
    }


async def test_auth_config_resolves_bot_username_from_token_once(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.webapi.routes import auth as auth_routes

    calls = 0

    async def fake_fetch_bot_username() -> str:
        nonlocal calls
        calls += 1
        return "resolved_bot"

    auth_routes._clear_login_bot_username_cache()
    monkeypatch.setattr(auth_routes, "_fetch_login_bot_username", fake_fetch_bot_username)
    settings.webapi.auth_mode = "magic_link"
    settings.webapi.login_start_payload = "resolved_payload"

    async with client_factory() as client:
        first = await client.get("/api/auth/config")
        second = await client.get("/api/auth/config")

    assert first.status_code == 200, first.text
    assert first.json() == {
        "auth_mode": "magic_link",
        "bot_username": "resolved_bot",
        "bot_start_url": "https://t.me/resolved_bot?start=resolved_payload",
    }
    assert second.json() == first.json()
    assert calls == 1


async def test_auth_config_without_bot_username_degrades_when_get_me_fails(
    client_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.webapi.routes import auth as auth_routes

    calls = 0

    async def fail_fetch_bot_username() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("telegram unavailable")

    auth_routes._clear_login_bot_username_cache()
    monkeypatch.setattr(auth_routes, "_fetch_login_bot_username", fail_fetch_bot_username)
    settings.webapi.auth_mode = "magic_link"
    settings.webapi.login_start_payload = "resolved_payload"

    async with client_factory() as client:
        first = await client.get("/api/auth/config")
        second = await client.get("/api/auth/config")

    assert first.status_code == 200, first.text
    assert first.json() == {"auth_mode": "magic_link"}
    assert second.json() == first.json()
    assert calls == 1


async def test_auth_config_does_not_expose_secrets_or_admins(client_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.webapi.routes import auth as auth_routes

    async def fake_fetch_bot_username() -> str:
        return "resolved_bot"

    monkeypatch.setattr(auth_routes, "_fetch_login_bot_username", fake_fetch_bot_username)
    settings.webapi.auth_mode = "telegram"

    async with client_factory() as client:
        resp = await client.get("/api/auth/config")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    forbidden = {
        "admin_super_admins",
        "bot_token",
        "moderator_bot_token",
        "session_cookie_name",
        "session_cookie_secure",
        "public_url",
        "login_start_payload",
    }
    assert body == {"auth_mode": "telegram", "bot_username": "resolved_bot"}
    assert forbidden.isdisjoint(body)


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
        assert me.json()["auth_mode"] == "telegram"

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


async def test_magic_link_flow(client_factory, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    from app.db.magic_link_store import create_magic_link

    settings.webapi.auth_mode = "magic_link"

    async with db_session_maker() as session:
        token, _ = await create_magic_link(session, user_id=268388996, ttl_minutes=15)

    async with client_factory() as client:
        bad = await client.post("/api/auth/magic-link", json={"token": "wrong"})
        assert bad.status_code == 401

        resp = await client.post("/api/auth/magic-link", json={"token": token})
        assert resp.status_code == 200, resp.text
        assert resp.cookies.get(settings.webapi.session_cookie_name)
        assert resp.json()["auth_mode"] == "magic_link"

        reused = await client.post("/api/auth/magic-link", json={"token": token})
        assert reused.status_code == 401

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == 268388996
