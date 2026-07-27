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
| `MCP_INITIATOR_ID` | Telegram ID of the admin the token acts as. No default; `propose_ban` and `propose_blacklist` refuse while unset. |

The cap bounds what a leaked token can cost: the endpoint cannot publish, but
each generation spends model budget and puts a message in a review chat.

`MCP_INITIATOR_ID` exists because a ban is an attributable act while the token
names a runtime. It is recorded on every proposal and carried into the decision
log, and it is also where the confirmation request is sent — so it must be a
super admin, or nobody will be able to press the button.

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

**This endpoint is not published to the internet.** The bot container binds
`MCP_PORT` on `127.0.0.1` only, and the edge proxy has no rule for it: the
`/api/*` rule in `docker/Caddyfile` points at `webapi`, which no longer carries
the control plane. Reaching it is a local-network concern — a client on the
host, or a private link such as WireGuard, Tailscale or an SSH tunnel.

This is a change from the earlier arrangement, where the endpoint lived on the
web API behind the existing `/api/*` rule and turning `MCP_ENABLED` on was
enough to publish it. Do not restore that by adding an edge rule for
`bot:8788`; the toolset now includes privileged moderation, and its safety
rests on more than the bearer token.

Authentication still applies on the local network. An unauthenticated request
is rejected before any MCP session is established and returns `401` with
`WWW-Authenticate: Bearer`.

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
