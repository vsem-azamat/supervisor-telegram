"""MCP endpoint: the admin control plane for an external agent runtime.

A second control plane alongside the cookie-authenticated web UI, for a runtime
(a Hermes gateway, say) that talks to the operator in their own chat surface.

The boundary is not the tool list — it is what a leaked token can do:

* **Reads** answer freely, but never outside what this deployment manages —
  see the peer resolver in ``app.mcp.deps``, which matters most for the tools
  backed by a Telethon user session that can otherwise see a whole account.
* **Bounded writes** — mute, unmute, unban, welcome text — take effect on the
  call. Each is reversible or self-expiring.
* **Removals** are not performed at all. ``propose_ban`` and
  ``propose_blacklist`` create a pending action and return; a super admin
  presses confirm in the moderator bot, or it expires having done nothing.

There is no tool that analyses a message and acts on its own verdict. One
existed on the removed assistant, and it decided *and* executed in a single
call, which is a straight path around the confirmation tier. Judgement belongs
to the runtime reading these tools, and to the human pressing confirm.

Authentication is a shared bearer token (``MCP_TOKEN``), not an admin session,
and the token is also the switch: no token, no endpoint. Because it names a
runtime rather than a person, and a ban is an attributable act, every proposal
is recorded against the first super admin — overridable, but never absent.

Served by the bot process (see ``app.mcp.runner``), not the web API: the
Telethon session and the confirmation handlers both live there.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = get_logger("webapi.mcp")

_MCP_INSTRUCTIONS = """Moderation tools for supervisor-telegram.

Chats are identified by their numeric Telegram ID (negative, e.g.
-1001234567890), never by @username. Call list_chats first to resolve one.
Anything absent from that list is refused.

propose_ban and propose_blacklist do not remove anyone. They put a request in
front of a super admin and return a pending id; a human presses confirm, or the
request expires on its own and nothing happens. Tell the operator what is
waiting for them rather than reporting the action as done.

Mutes, unmutes and unbans do take effect immediately — each is bounded or
restores access.
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
    from app.mcp.tools.moderate import register_moderation_tools
    from app.mcp.tools.read import register_read_tools

    register_read_tools(mcp)
    register_moderation_tools(mcp)

    return mcp


def build_mcp_asgi_app(token: str, path: str = "/") -> Any:
    """Build the token-protected ASGI app the bot process serves."""
    from starlette.middleware import Middleware

    mcp = build_mcp_server()
    return mcp.http_app(
        path=path,
        middleware=[Middleware(BearerTokenMiddleware, token=token)],
    )
