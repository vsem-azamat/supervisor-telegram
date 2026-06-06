# Admin Web

The web surface has a public read layer and an authenticated admin layer.

## Core Rules

- Public visitors may access only explicitly public, read-only endpoints.
- The current public endpoint is `GET /api/public/catalog`.
- Public responses must expose only fields intended for anonymous viewers.
- Administrative reads and all mutations require an authenticated admin session.
- Authentication shortcuts or bypass flags are not valid production or remote
  development behavior.
- Magic links are an administrator access mechanism and must be generated only
  through trusted admin-only flows.
- `GET /api/auth/config` is public and may expose only the active web auth mode
  plus non-secret UI hints such as the Telegram bot start URL used to request a
  trusted magic link. It must not expose admin IDs, tokens, session values, or
  provider credentials.
- The login page must render the mechanism selected by `WEBAPI_AUTH_MODE`.
  Telegram Login Widget is valid only for `telegram` mode and only on domains
  configured in BotFather. `magic_link` mode must not load the Telegram widget;
  it should accept a one-time token from the URL and otherwise offer a Telegram
  bot deep link that asks the bot to issue a trusted magic link.
- The Telegram bot deep link for web admin login uses the code-owned
  `/start web_admin_login` payload and the moderator bot username. The username
  is resolved from `MODERATOR_BOT_TOKEN` through Telegram `getMe()` and cached
  for the process. In `magic_link` mode, the bot may issue a one-time web login
  URL only to the configured main super admin. It must not put reusable
  credentials or raw session values in the public login page.
- Production and remote development must use separate Telegram bot tokens. The
  web-login `/start` payload is not an environment-specific routing knob; bot
  identity separates environments.

## Tests

- Anonymous access tests must prove the public projection is available and does
  not leak admin-only fields.
- Protected endpoint tests must prove anonymous requests are rejected.
- Authenticated tests must prove allowed admin actions still succeed.
- Auth configuration tests must prove the public config endpoint exposes the
  selected mode without exposing secrets or admin-only fields.
- Magic-link UI tests must prove the login page offers the bot deep link without
  loading Telegram Login Widget.
- Telegram handler tests must prove the web-login deep link issues a
  one-time web login URL only through the trusted bot conversation.
- UI tests should preserve the distinction between public browsing and
  authenticated administration.
