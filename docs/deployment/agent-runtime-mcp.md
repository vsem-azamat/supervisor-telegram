# Exposing the MCP Endpoint to an Agent Runtime

Operational contract for running the MCP endpoint described in
[Agent Control Plane](../domain/agent-control-plane.md). Behavioral rules live
there; this document covers configuration and network exposure.

## Configuration

| Variable | Meaning |
| --- | --- |
| `MCP_ENABLED` | Mount the endpoint. Default `false`. |
| `MCP_TOKEN` | Shared bearer token the client must present. No default. |
| `MCP_PATH` | Mount path. Default `/api/mcp`. |
| `MCP_MAX_DRAFTS_PER_HOUR` | Cap on `generate_and_send_for_review` calls per hour. Default `10`; `0` disables the cap. |

The cap bounds what a leaked token can cost: the endpoint cannot publish, but
each generation spends model budget and puts a message in a review chat. It is
counted in-process, so it is per worker if the web API is ever scaled beyond the
single uvicorn worker it runs today.

Both `MCP_ENABLED=true` and a non-empty `MCP_TOKEN` are required; either alone
leaves the endpoint unmounted. The token is a production credential and belongs
in the VPS `.env` alongside the bot tokens — see
[Production Credentials](production-credentials.md). Generate it with
`openssl rand -hex 32` and rotate it by editing `.env` and restarting `webapi`.

The endpoint lives in the `webapi` process. Enabling it does not touch the `bot`
process, and approve/reject callbacks continue to be handled there.

## Network exposure

**The default deployment already publishes this path.** `docker/Caddyfile`
proxies `/api/*` to `webapi:8787`, and the server-level edge Caddy fronts that,
so turning `MCP_ENABLED` on makes `/api/mcp` reachable from the public internet
with the bearer token as the only control.

Prefer keeping it off the public internet:

- Reach the endpoint over a private network — WireGuard, Tailscale, or an SSH
  tunnel from the machine running the agent runtime — and block `/api/mcp` at
  the edge Caddy.
- If it must be public, treat the token as an internet-facing secret: high
  entropy, rotated on any suspicion, never logged or pasted into agent chat
  history.

An unauthenticated request to the endpoint itself is rejected before any MCP
session is established and returns `401` with `WWW-Authenticate: Bearer`. Note
that `POST /api/mcp` without the trailing slash is redirected (`307`) by the
parent router before authentication runs, so an unauthenticated prober can still
tell that the endpoint is mounted. Treat its existence as public and the token as
the only secret.

## Client configuration

The endpoint speaks Streamable HTTP at `<base-url>/api/mcp/` (trailing slash).
An MCP client is configured with the URL and a static `Authorization` header. For
a Hermes gateway that is an entry under `mcp_servers` in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  supervisor-telegram:
    url: "https://<host>/api/mcp/"
    headers:
      Authorization: "Bearer <MCP_TOKEN>"
    timeout: 180
```

## Verifying a deployment

```bash
# Expect 401 without credentials
curl -si -X POST https://<host>/api/mcp/ | head -1

# Expect an MCP protocol response (not 401) with them
curl -si -X POST https://<host>/api/mcp/ \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -1
```

`tools/list` must return exactly `list_channels`, `get_channel` and
`generate_and_send_for_review`. Anything else means the toolset drifted from the
documented boundary.
