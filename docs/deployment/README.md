# Deployment

This section covers production runtime operations and deployment contracts.

- [Production Credentials](production-credentials.md) - where production
  credentials live, which values must be real production values, and how to
  rotate or audit them without printing secrets.

## Web Origin Routing

The public web admin origin must be a single HTTPS origin with path-based
routing at the edge proxy:

- `/api/*` routes to the FastAPI web API service.
- all other paths route to the web UI service.

This contract applies to production and remote development domains such as
`dev.konnekt.azamat.io`. Remote development may expose a Vite web UI through the
edge for native browser testing, but `/api/*` must still be routed by the edge
directly to FastAPI. Vite's local `/api` proxy is only a localhost developer
convenience; do not rely on Vite as the public API proxy for remote browser
testing.

Remote development domains that use Telegram Login Widget must be configured in
BotFather for the bot used by the UI. If the domain is not configured in
BotFather, use `WEBAPI_AUTH_MODE=magic_link` for that environment instead of
loading the Telegram widget.

Remote development must use a development Telegram bot token. Do not point a
remote development instance at the production `MODERATOR_BOT_TOKEN`; Telegram
updates and Bot API writes belong to the bot token, not to the web domain.

## Web Smoke Check

After changing web routing, auth mode, TLS, or public domain configuration, run
a smoke check against the public HTTPS origin:

```bash
curl -fsS https://dev.konnekt.azamat.io/api/health
curl -fsS https://dev.konnekt.azamat.io/api/auth/config
curl -fsS https://dev.konnekt.azamat.io/api/public/catalog
curl -fsSI https://dev.konnekt.azamat.io/
```

Expected results:

- `/api/health` returns `{"status":"ok"}`.
- `/api/auth/config` returns the active auth mode, optional non-secret bot
  start URL, and no secrets.
- `/api/public/catalog` returns public catalog JSON.
- `/` returns an HTML response from the web UI.
