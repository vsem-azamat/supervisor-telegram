"""MCP endpoint exposing a read-plus-review toolset to external agent clients.

This is a second admin control plane alongside the cookie-authenticated web UI,
intended for an external agent runtime (e.g. a Hermes gateway) that talks to the
operator in Telegram. It deliberately exposes a narrow surface:

* reads — ``list_channels`` and ``get_channel``;
* one write — ``generate_and_send_for_review``, which can only put a draft in
  front of a human in the channel's review chat.

There is no publish, ban, blacklist or delete tool here, and the review path
refuses channels that have no review chat rather than falling back to publishing
directly. The approve/reject decision stays where it already is: the inline
keyboard handled by the bot process. An external agent can therefore propose
content but cannot make anything public on its own.

Authentication is a shared bearer token (``MCP_TOKEN``), not an admin session.
It identifies the calling runtime, not a person, so it grants exactly the
toolset above regardless of who is chatting with that runtime.
"""

from __future__ import annotations

import hmac
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = get_logger("webapi.mcp")

_MCP_INSTRUCTIONS = """Admin tools for the supervisor-telegram content pipeline.

Channels are identified by their numeric Telegram ID (negative, e.g.
-1001234567890), not by @username. Call list_channels first to resolve one.

generate_and_send_for_review writes a draft into the channel's review chat where
a human approves or rejects it with inline buttons. It never publishes. Nothing
you do here reaches a channel's audience without that human approval.
"""


class BearerTokenMiddleware:
    """Reject requests without a matching ``Authorization: Bearer`` token.

    Runs as raw ASGI in front of the MCP transport so an unauthenticated caller
    is turned away before any MCP session is established.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        # An empty token would make compare_digest succeed against an empty
        # credential, turning this into an open door. Callers gate on
        # settings.mcp.active, but an auth component must enforce its own
        # precondition rather than trust that.
        if not token:
            raise ValueError("BearerTokenMiddleware requires a non-empty token")
        self.app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        if scope_type == "lifespan":
            # Starlette dispatches lifespan through the middleware stack; it
            # carries no credentials and must reach the transport.
            await self.app(scope, receive, send)
            return

        if scope_type != "http":
            # The MCP transport exposes no other protocol. Refuse rather than
            # forward something this middleware cannot authenticate.
            await send({"type": "websocket.close", "code": 1008})
            return

        if not self._authorized(scope):
            await self._unauthorized(send)
            return

        await self.app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        headers = [value for name, value in scope.get("headers", []) if name.lower() == b"authorization"]
        # Exactly one credential, or none at all. Two Authorization headers have
        # no agreed meaning and intermediaries disagree on which one wins, so
        # accepting either would make the decision depend on the proxy chain.
        if len(headers) != 1:
            return False

        scheme, _, presented = headers[0].decode("latin-1").partition(" ")
        if scheme.lower() != "bearer":
            return False
        # compare_digest keeps the check constant-time; both sides are encoded
        # first so a non-ASCII token cannot raise here.
        return hmac.compare_digest(presented.strip().encode(), self._token.encode())

    async def _unauthorized(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})


class RateLimiter:
    """Sliding-window cap on how often a tool may run.

    Generation is the expensive tool: each call spends model budget and puts a
    message in a review chat. The endpoint cannot publish, but a leaked token
    could still burn money and flood the operator, so the cost is bounded here.

    In-process state is enough because the web API runs a single uvicorn worker
    (``scripts/entrypoint.sh``); with multiple workers this becomes per-worker.
    """

    def __init__(self, limit: int, window_seconds: float = 3600.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        """Record and admit a call, or refuse it when the window is full."""
        if self._limit <= 0:
            return True
        now = time.monotonic()
        while self._hits and now - self._hits[0] >= self._window:
            self._hits.popleft()
        if len(self._hits) >= self._limit:
            return False
        self._hits.append(now)
        return True


def _channel_summary(channel: Any) -> dict[str, Any]:
    """Project a Channel row into the shape agent clients consume."""
    return {
        "channel_id": channel.telegram_id,
        "username": channel.username,
        "name": channel.name,
        "language": channel.language,
        "enabled": channel.enabled,
        "has_review_chat": bool(channel.review_chat_id),
        "max_posts_per_day": channel.max_posts_per_day,
        "posts_today": channel.daily_posts_count,
        "description": channel.description or "",
    }


def build_mcp_server() -> FastMCP[None]:
    """Construct the MCP server and register its tools."""
    from fastmcp import FastMCP

    mcp: FastMCP[None] = FastMCP(
        name="supervisor-telegram",
        instructions=_MCP_INSTRUCTIONS,
        # Unhandled exceptions would otherwise be returned verbatim to the
        # calling runtime — a failed DB connect leaks its DSN, credentials and
        # all, into an external agent's context and from there into chat history.
        mask_error_details=True,
    )
    from app.core.config import settings

    draft_limiter = RateLimiter(settings.mcp.max_drafts_per_hour)

    @mcp.tool
    async def list_channels() -> dict[str, Any]:
        """List every channel the pipeline manages, with its review-chat status.

        Use this to resolve a channel name or @username into the numeric
        channel_id that the other tools require.
        """
        from sqlalchemy import select

        from app.db.models import Channel
        from app.db.session import create_session_maker

        session_maker = create_session_maker()
        async with session_maker() as session:
            rows = (await session.execute(select(Channel).order_by(Channel.id))).scalars().all()
        return {"channels": [_channel_summary(row) for row in rows]}

    @mcp.tool
    async def get_channel(channel_id: int, recent_posts: int = 5) -> dict[str, Any]:
        """Get one channel's configuration and its most recent posts.

        channel_id is the numeric Telegram ID from list_channels. recent_posts
        caps how many recent posts to include (1-50); each shows its review
        status, so you can see what is waiting for approval.
        """
        from sqlalchemy import select

        from app.channel.channel_repo import get_channel_by_telegram_id
        from app.db.models import ChannelPost
        from app.db.session import create_session_maker

        session_maker = create_session_maker()
        channel = await get_channel_by_telegram_id(session_maker, channel_id)
        if channel is None:
            return {"error": "channel_not_found", "channel_id": channel_id}

        limit = min(max(1, recent_posts), 50)
        async with session_maker() as session:
            posts = (
                (
                    await session.execute(
                        select(ChannelPost)
                        .where(ChannelPost.channel_id == channel_id)
                        .order_by(ChannelPost.id.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

        summary = _channel_summary(channel)
        summary["posting_schedule"] = list(channel.posting_schedule or [])
        summary["publish_schedule"] = list(channel.publish_schedule or [])
        summary["discovery_query"] = channel.discovery_query or ""
        summary["recent_posts"] = [
            {"post_id": post.id, "status": post.status, "title": post.title or ""} for post in posts
        ]
        return summary

    @mcp.tool
    async def generate_and_send_for_review(
        channel_id: int,
        topic: str,
        source_url: str = "",
    ) -> dict[str, Any]:
        """Generate a post about a topic and send it to the channel's review chat.

        A human approves or rejects it there — this tool never publishes. It
        fails if the channel has no review chat configured.

        topic must carry the full story: headline, key facts and context. A vague
        one-line summary produces a poor post. source_url should be the article
        URL when the topic came from a specific source.
        """
        from app.channel.adhoc import generate_for_review
        from app.db.session import create_session_maker
        from app.webapi.services.review_bot import build_review_bot, close_review_bot

        if not draft_limiter.allow():
            logger.warning("mcp_draft_rate_limited", channel_id=channel_id)
            return {
                "status": "rate_limited",
                "channel_id": channel_id,
                "detail": (
                    "Too many drafts requested in the last hour. Wait before generating more, "
                    "and tell the operator rather than retrying."
                ),
            }

        review_bot = build_review_bot()
        try:
            result = await generate_for_review(
                session_maker=create_session_maker(),
                review_bot=review_bot,
                channel_id=channel_id,
                topic=topic,
                source_url=source_url,
                # No publish_bot on purpose: without it the service cannot take
                # its direct-publish path, so this endpoint is incapable of
                # making anything public regardless of channel configuration.
            )
        finally:
            await close_review_bot(review_bot)

        logger.info(
            "mcp_generate_and_send_for_review",
            channel_id=channel_id,
            status=result.status,
            post_id=result.post_id,
        )
        payload: dict[str, Any] = {
            "status": result.status,
            "channel_id": channel_id,
            "post_id": result.post_id,
            "preview": result.preview,
        }
        if result.status == "no_review_chat":
            payload["detail"] = (
                "This channel has no review chat, so a generated post could only be "
                "published directly. Configure a review chat first."
            )
        return payload

    return mcp


def build_mcp_asgi_app(token: str, path: str = "/") -> Any:
    """Build the token-protected ASGI app to mount on the web API."""
    from starlette.middleware import Middleware

    mcp = build_mcp_server()
    return mcp.http_app(
        path=path,
        middleware=[Middleware(BearerTokenMiddleware, token=token)],
    )
