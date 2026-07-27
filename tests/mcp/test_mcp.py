"""MCP endpoint: serving, bearer auth, and the exposed toolset's boundaries.

The security-relevant claims under test: the endpoint is absent unless explicitly
configured, it rejects callers without the shared token, and the toolset cannot
publish — a channel with no review chat is refused rather than published to.
"""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.db.models import Channel, ChannelPost
from app.mcp.server import BearerTokenMiddleware, build_mcp_server
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

CHANNEL_ID = -1001234567890
TOKEN = "test-mcp-token"  # noqa: S105 — test fixture, not a credential


@pytest.fixture
def mcp_settings():
    """Enable the MCP endpoint for the duration of a test."""
    original = settings.mcp.token
    settings.mcp.token = TOKEN
    yield
    settings.mcp.token = original


@pytest.fixture
def mcp_session(db_session_maker, monkeypatch):
    """Point the MCP tools at the in-memory test database."""
    from app.db import session as session_module

    monkeypatch.setattr(session_module, "create_session_maker", lambda: db_session_maker)
    return db_session_maker


async def _seed_channel(session_maker, *, review_chat_id: int | None) -> None:
    async with session_maker() as session:
        session.add(
            Channel(
                telegram_id=CHANNEL_ID,
                name="Test Channel",
                language="ru",
                review_chat_id=review_chat_id,
                username="testchan",
            )
        )
        await session.commit()


async def _call(tool: str, args: dict | None = None):
    from fastmcp import Client

    async with Client(build_mcp_server()) as client:
        result = await client.call_tool(tool, args or {})
    return result.data


# ── serving ───────────────────────────────────────────────────────────────


async def test_runner_is_a_no_op_when_not_configured() -> None:
    """Default config must not expose an admin control plane."""
    from app.mcp.runner import run_mcp_server

    # Returns rather than binding a port: nothing to cancel, nothing listening.
    await run_mcp_server()


async def test_web_api_no_longer_carries_the_endpoint(mcp_settings) -> None:
    """The control plane moved to the bot process; the web API must not re-mount it.

    Two live endpoints would mean two Telethon clients on one session file.
    """
    from app.webapi.main import create_app

    app = create_app()
    assert not any(getattr(route, "path", "").startswith("/api/mcp") for route in app.routes)


async def test_app_answers_on_the_configured_path(mcp_settings) -> None:
    from app.mcp.server import build_mcp_asgi_app

    app = build_mcp_asgi_app(token=TOKEN, path=settings.mcp.path)
    assert any(getattr(route, "path", "") == settings.mcp.path for route in app.routes)


async def test_without_a_token_it_stays_closed() -> None:
    """The token is the switch; there is no second one to disagree with it."""
    original = settings.mcp.token
    settings.mcp.token = ""
    try:
        assert settings.mcp.active is False
    finally:
        settings.mcp.token = original


# ── authentication ────────────────────────────────────────────────────────


async def _middleware_call(headers: list[tuple[bytes, bytes]]) -> tuple[bool, int | None]:
    """Drive the middleware directly; report whether the inner app was reached."""
    reached = False

    async def inner(scope, receive, send) -> None:
        nonlocal reached
        reached = True

    status: int | None = None

    async def send(message) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = BearerTokenMiddleware(inner, token=TOKEN)
    await middleware({"type": "http", "headers": headers}, receive, send)
    return reached, status


async def test_correct_token_reaches_the_transport() -> None:
    reached, status = await _middleware_call([(b"authorization", f"Bearer {TOKEN}".encode())])
    assert reached is True
    assert status is None


@pytest.mark.parametrize(
    ("headers", "case"),
    [
        ([], "no authorization header"),
        ([(b"authorization", b"Bearer wrong-token")], "wrong token"),
        ([(b"authorization", b"Basic " + TOKEN.encode())], "wrong scheme"),
        ([(b"authorization", b"Bearer ")], "empty token"),
        ([(b"authorization", TOKEN.encode())], "bare token without scheme"),
        (
            [(b"authorization", f"Bearer {TOKEN}".encode()), (b"authorization", b"Bearer nope")],
            "duplicate headers, valid first",
        ),
        (
            [(b"authorization", b"Bearer nope"), (b"authorization", f"Bearer {TOKEN}".encode())],
            "duplicate headers, valid second",
        ),
        ([(b"authorization", f"Bearer {TOKEN} extra".encode())], "trailing garbage"),
    ],
)
async def test_bad_credentials_rejected(headers, case) -> None:
    reached, status = await _middleware_call(headers)
    assert reached is False, case
    assert status == 401, case


async def test_scheme_matching_is_case_insensitive() -> None:
    """RFC 7235 makes the auth scheme case-insensitive; clients vary."""
    reached, _ = await _middleware_call([(b"authorization", f"bearer {TOKEN}".encode())])
    assert reached is True


async def test_middleware_refuses_to_be_built_without_a_token() -> None:
    """An empty token would match an empty credential and open the door."""

    async def inner(scope, receive, send) -> None:  # pragma: no cover - never called
        raise AssertionError("must not be reachable")

    with pytest.raises(ValueError, match="non-empty token"):
        BearerTokenMiddleware(inner, token="")


async def test_non_http_scope_is_not_forwarded() -> None:
    """Only HTTP is authenticated here, so nothing else may pass through."""
    reached = False

    async def inner(scope, receive, send) -> None:
        nonlocal reached
        reached = True

    sent: list[dict] = []

    async def send(message) -> None:
        sent.append(message)

    async def receive() -> dict:
        return {"type": "websocket.connect"}

    middleware = BearerTokenMiddleware(inner, token=TOKEN)
    await middleware({"type": "websocket", "headers": []}, receive, send)

    assert reached is False
    assert sent == [{"type": "websocket.close", "code": 1008}]


async def test_unauthenticated_request_over_http_gets_401(mcp_settings) -> None:
    from app.mcp.server import build_mcp_asgi_app

    app = build_mcp_asgi_app(token=TOKEN, path="/api/mcp")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/mcp", json={"jsonrpc": "2.0", "method": "tools/list"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_authenticated_request_works_with_the_app_lifespan_running(mcp_settings) -> None:
    """The MCP transport needs its session manager started by the app lifespan.

    Without a running lifespan every authenticated call fails at runtime, while
    every other test here still passes because they stop at the auth boundary.
    This is the test that fails if the runner stops driving the lifespan.
    """
    from app.mcp.server import build_mcp_asgi_app

    app = build_mcp_asgi_app(token=TOKEN, path="/api/mcp")
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/mcp",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                },
            )

    assert response.status_code == 200, response.text
    assert response.headers.get("mcp-session-id")


# ── tool behaviour ────────────────────────────────────────────────────────


async def test_list_channels_reports_review_chat_status(mcp_session) -> None:
    await _seed_channel(mcp_session, review_chat_id=-100500)

    data = await _call("list_channels")

    assert len(data["channels"]) == 1
    channel = data["channels"][0]
    assert channel["channel_id"] == CHANNEL_ID
    assert channel["username"] == "testchan"
    assert channel["has_review_chat"] is True


async def test_get_channel_includes_recent_posts(mcp_session) -> None:
    await _seed_channel(mcp_session, review_chat_id=-100500)
    async with mcp_session() as session:
        session.add(ChannelPost(channel_id=CHANNEL_ID, external_id="e1", title="Older", post_text="a", status="draft"))
        session.add(
            ChannelPost(channel_id=CHANNEL_ID, external_id="e2", title="Newer", post_text="b", status="approved")
        )
        await session.commit()

    data = await _call("get_channel", {"channel_id": CHANNEL_ID})

    assert data["channel_id"] == CHANNEL_ID
    titles = [post["title"] for post in data["recent_posts"]]
    assert titles == ["Newer", "Older"]


async def test_get_channel_unknown_id(mcp_session) -> None:
    data = await _call("get_channel", {"channel_id": -1009999999999})
    assert data["error"] == "channel_not_found"


async def test_review_request_refused_without_review_chat(mcp_session, monkeypatch) -> None:
    """The endpoint must not be able to make anything public.

    Without a review chat the shared service would publish directly, so the tool
    has to refuse before generating anything.
    """
    from unittest.mock import AsyncMock

    await _seed_channel(mcp_session, review_chat_id=None)
    generate = AsyncMock()
    monkeypatch.setattr("app.channel.generator.generate_post", generate)

    data = await _call(
        "generate_and_send_for_review",
        {"channel_id": CHANNEL_ID, "topic": "Full story with facts"},
    )

    assert data["status"] == "no_review_chat"
    generate.assert_not_awaited()


async def test_review_request_sends_draft_for_approval(mcp_session, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    await _seed_channel(mcp_session, review_chat_id=-100500)
    monkeypatch.setattr(
        "app.channel.generator.generate_post",
        AsyncMock(return_value=SimpleNamespace(text="Draft body", image_url=None, image_urls=[])),
    )
    send = AsyncMock(return_value=99)
    monkeypatch.setattr("app.channel.review.send_for_review", send)

    # build_review_bot is synchronous — a MagicMock keeps it returning a bot
    # rather than a coroutine, so the bot actually reaches the service.
    review_bot = AsyncMock()
    monkeypatch.setattr("app.webapi.services.review_bot.build_review_bot", MagicMock(return_value=review_bot))
    close = AsyncMock()
    monkeypatch.setattr("app.webapi.services.review_bot.close_review_bot", close)

    data = await _call(
        "generate_and_send_for_review",
        {"channel_id": CHANNEL_ID, "topic": "Full story with facts"},
    )

    assert data["status"] == "sent_for_review"
    assert data["post_id"] == 99
    assert data["preview"] == "Draft body"
    assert send.await_args is not None
    assert send.await_args.kwargs["bot"] is review_bot
    close.assert_awaited_once_with(review_bot)


async def test_review_bot_session_closed_when_generation_raises(mcp_session, monkeypatch) -> None:
    """A failing generation must not leak the outgoing bot's HTTP session."""
    from unittest.mock import AsyncMock, MagicMock

    await _seed_channel(mcp_session, review_chat_id=-100500)
    monkeypatch.setattr("app.channel.generator.generate_post", AsyncMock(side_effect=RuntimeError("boom")))
    review_bot = AsyncMock()
    monkeypatch.setattr("app.webapi.services.review_bot.build_review_bot", MagicMock(return_value=review_bot))
    close = AsyncMock()
    monkeypatch.setattr("app.webapi.services.review_bot.close_review_bot", close)

    data = await _call(
        "generate_and_send_for_review",
        {"channel_id": CHANNEL_ID, "topic": "Full story with facts"},
    )

    assert data["status"] == "generation_failed"
    close.assert_awaited_once_with(review_bot)


async def test_tool_never_hands_the_service_a_publish_bot(mcp_session, monkeypatch) -> None:
    """Pins the invariant at the call site, not just in the service.

    The service refuses to publish only because no publish bot is passed. A
    future edit adding one here would restore the direct-publish path, and
    nothing else in the suite would notice.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.channel.adhoc import AdhocResult

    await _seed_channel(mcp_session, review_chat_id=-100500)
    generate = AsyncMock(return_value=AdhocResult(status="sent_for_review", post_id=5))
    monkeypatch.setattr("app.channel.adhoc.generate_for_review", generate)
    monkeypatch.setattr("app.webapi.services.review_bot.build_review_bot", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr("app.webapi.services.review_bot.close_review_bot", AsyncMock())

    await _call(
        "generate_and_send_for_review",
        {"channel_id": CHANNEL_ID, "topic": "Full story with facts"},
    )

    assert generate.await_args is not None
    assert generate.await_args.kwargs.get("publish_bot") is None


async def test_rate_limit_refuses_further_drafts(mcp_session, monkeypatch) -> None:
    """A leaked token must not be able to burn model budget without bound."""
    from unittest.mock import AsyncMock, MagicMock

    from app.channel.adhoc import AdhocResult

    await _seed_channel(mcp_session, review_chat_id=-100500)
    monkeypatch.setattr(settings.mcp, "max_drafts_per_hour", 1)
    generate = AsyncMock(return_value=AdhocResult(status="sent_for_review", post_id=5))
    monkeypatch.setattr("app.channel.adhoc.generate_for_review", generate)
    monkeypatch.setattr("app.webapi.services.review_bot.build_review_bot", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr("app.webapi.services.review_bot.close_review_bot", AsyncMock())

    from fastmcp import Client

    args = {"channel_id": CHANNEL_ID, "topic": "Full story with facts"}
    async with Client(build_mcp_server()) as client:
        first = (await client.call_tool("generate_and_send_for_review", args)).data
        second = (await client.call_tool("generate_and_send_for_review", args)).data

    assert first["status"] == "sent_for_review"
    assert second["status"] == "rate_limited"
    assert generate.await_count == 1


async def _tool_names() -> set[str]:
    from fastmcp import Client

    async with Client(build_mcp_server()) as client:
        return {tool.name for tool in await client.list_tools()}


async def test_exposed_surface_is_pinned() -> None:
    """Growing the surface should be a deliberate act, so compare as a set."""
    assert await _tool_names() == {
        # content
        "list_channels",
        "get_channel",
        "generate_and_send_for_review",
        # reads
        "list_chats",
        "get_blacklist",
        "get_chat_info",
        "get_user_info",
        "get_moderation_history",
        "get_chat_history",
        "search_messages",
        "get_chat_members",
        # bounded writes
        "mute_user",
        "unmute_user",
        "unban_user",
        "unblacklist_user",
        "set_welcome",
        # confirm tier
        "propose_ban",
        "propose_blacklist",
    }


async def test_nothing_here_removes_a_person_on_its_own() -> None:
    """The names that would bypass confirmation, called out by name.

    The set assertion above already fails on any addition, but it fails the
    same way for a harmless one. These say which additions are the dangerous
    kind, so a future reader sees the reason rather than a diff.
    """
    names = await _tool_names()

    assert "ban_user" not in names
    assert "blacklist_user" not in names
    assert "publish_text" not in names
    assert "send_message" not in names
    # Runs the moderation agent and then executes its verdict, up to a global
    # blacklist — a straight path around the confirmation tier.
    assert "analyze_message" not in names
