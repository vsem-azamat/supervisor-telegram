# Exposing the MCP Endpoint to an Agent Runtime

Configuration and network exposure for the MCP control plane. The rules that
govern its behaviour are in [Invariants](../invariants.md).

## Configuration

| Variable | Meaning |
| --- | --- |
| `MCP_TOKEN` | Shared bearer token the client must present, and the switch: no token, no endpoint. |
| `MCP_MAX_DRAFTS_PER_HOUR` | Cap on `generate_and_send_for_review` calls per hour. Default `10`; `0` disables the cap. |

The cap bounds what a leaked token can cost: the endpoint cannot publish, but
each generation spends model budget and puts a message in a review chat.

A ban is an attributable act while the token names a runtime, so proposals are
recorded against the first super admin, which is also where the confirmation is
sent. `MCP_INITIATOR_ID` overrides that if the token should answer to someone
else on the list.

The token is the only switch: unset means no endpoint. Path and port are fixed
in code at `/api/mcp` and `8788`, because the compose port mapping hard-codes
the container side and a configurable port would bind the app to a number the
mapping does not forward.

The token is a production credential and lives as a GitHub secret — see
[Production Credentials](production-credentials.md). Generate it with
`openssl rand -hex 32`; rotate it by updating the secret and re-running the
deploy workflow.

## Which process serves it

The `bot` process, not `webapi`. Moderation tools need the Telethon user
session, whose SQLite file only one process may open, and the escalation timers,
which are asyncio tasks belonging to whichever process created them. Both are in
`bot`.

Restarting `bot` therefore drops MCP connections along with polling, and
`webapi` can be restarted without touching the control plane.

## Network exposure

**This endpoint is not published to the internet.** The bot container binds
port 8788 on `127.0.0.1` only, and the edge proxy has no rule for it: the
`/api/*` rule in `docker/Caddyfile` points at `webapi`, which no longer carries
the control plane. Reaching it is a local-network concern — a client on the
host, or a private link such as WireGuard, Tailscale or an SSH tunnel.

This is a change from the earlier arrangement, where the endpoint lived on the
web API behind the existing `/api/*` rule and setting a token was
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
