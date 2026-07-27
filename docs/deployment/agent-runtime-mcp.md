# Exposing the MCP Endpoint to an Agent Runtime

Configuration and network exposure for the MCP control plane. The rules that
govern its behaviour are in [Invariants](../invariants.md).

## Configuration

| Variable | Meaning |
| --- | --- |
| `MCP_ENABLED` | Serve the endpoint. Default `false`. |
| `MCP_TOKEN` | Shared bearer token the client must present. No default. |
| `MCP_PATH` | Path the endpoint answers on. Default `/api/mcp`. |
| `MCP_PORT` | Port the bot process listens on. Default `8788`, published loopback-only. |
| `MCP_MAX_DRAFTS_PER_HOUR` | Cap on `generate_and_send_for_review` calls per hour. Default `10`; `0` disables the cap. |

The cap bounds what a leaked token can cost: the endpoint cannot publish, but
each generation spends model budget and puts a message in a review chat.

Both `MCP_ENABLED=true` and a non-empty `MCP_TOKEN` are required; either alone
leaves the endpoint closed. The token is a production credential and belongs in
the VPS `.env` alongside the bot tokens — see
[Production Credentials](production-credentials.md). Generate it with
`openssl rand -hex 32` and rotate it by editing `.env` and restarting `bot`.

## Which process serves it

The `bot` process, not `webapi`. Moderation tools need the Telethon user
session, whose SQLite file only one process may open, and the escalation timers,
which are asyncio tasks belonging to whichever process created them. Both are in
`bot`.

Restarting `bot` therefore drops MCP connections along with polling, and
`webapi` can be restarted without touching the control plane.

## Network exposure

The bot container publishes `MCP_PORT` on `127.0.0.1` only. Nothing reaches the
endpoint from outside the host until the edge proxy is pointed at it — unlike
the previous arrangement under `webapi`, where the existing `/api/*` proxy rule
made enabling the flag sufficient to publish it.

Prefer keeping it off the public internet:

- Reach it over a private network — WireGuard, Tailscale, or an SSH tunnel from
  the machine running the agent runtime.
- If it must be public, add an explicit edge rule and treat the token as an
  internet-facing secret: high entropy, rotated on any suspicion, never logged
  or pasted into agent chat history.

An unauthenticated request is rejected before any MCP session is established and
returns `401` with `WWW-Authenticate: Bearer`. Routing answers before
authentication does, so an unauthenticated prober can still tell the endpoint
exists. Treat its existence as public and the token as the only secret.

## Client configuration

The endpoint speaks Streamable HTTP at `<base-url>/api/mcp`. An MCP client is
configured with the URL and a static `Authorization` header. For a Hermes
gateway that is an entry under `mcp_servers` in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  supervisor-telegram:
    url: "http://127.0.0.1:8788/api/mcp"
    headers:
      Authorization: "Bearer <MCP_TOKEN>"
    timeout: 180
```

## Verifying a deployment

```bash
# Expect 401 without credentials
curl -si -X POST http://127.0.0.1:8788/api/mcp | head -1

# Expect an MCP protocol response (not 401) with them
curl -si -X POST http://127.0.0.1:8788/api/mcp \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -1
```

The exposed toolset is pinned by a test, so drift shows up there first rather
than in a document that has to be kept in step by hand.
