# Production Credentials

This is the operational contract for production credentials. Keep real values
only in the VPS `~/deploy/supervisor-telegram/.env`, GitHub Actions secrets, or
the provider consoles. Do not commit real tokens, database passwords, Telethon
sessions, or exported `.env` files.

## Where Credentials Live

Production deploys from GitHub Actions on pushes to `main`.

- GitHub Actions secrets store only deploy access:
  - `VPS_HOST`
  - `VPS_USER`
  - `VPS_SSH_KEY`
- The application runtime credentials live on the VPS in:
  - `~/deploy/supervisor-telegram/.env`
- The Telethon userbot session is mounted from:
  - `~/deploy/supervisor-telegram/moderator_userbot.session`

The deploy workflow updates `IMAGE_TAG` in the VPS `.env` on each deploy. The
other values are managed manually on the VPS.

## Production Baseline

Use `.env.production.example` as the non-secret template for the VPS `.env`.

Required production values:

- `IMAGE_TAG`: maintained by GitHub Actions after deploy; needed for Docker
  Compose bootstrap.
- `MODERATOR_BOT_TOKEN`: production BotFather token, not a local/dev bot.
- `ADMIN_SUPER_ADMINS`: real Telegram user IDs for production admins.
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`: production
  PostgreSQL credentials.
- `OPENROUTER_API_KEY`: production LLM API key when any LLM-backed feature is
  enabled.
- `WEBAPI_PUBLIC_URL`: public HTTPS URL of the web UI.
- `WEBAPI_ALLOWED_ORIGINS`: the same public HTTPS origin as `WEBAPI_PUBLIC_URL`.
- `WEBAPI_SESSION_COOKIE_SECURE=true`: required for production HTTPS sessions.
- `WEBUI_PORT`: host port exposed by the static web UI container.

Feature-specific production values:

- `ASSISTANT_BOT_TOKEN`: required only when `ASSISTANT_BOT_ENABLED=true`.
- `BRAVE_API_KEY`: required only when Brave-backed discovery is enabled.
- `TELETHON_API_ID`, `TELETHON_API_HASH`, and `moderator_userbot.session`:
  required only when `TELETHON_ENABLED=true`.
- `SPONSORED_ADS_MODERATOR_CHAT_ID` and `SPONSORED_ADS_SALES_CONTACT`: required
  for the sponsored-ads funnel to send review alerts and show a sales contact.

## Dev Values To Remove From Production

These values are development-only or stale and should not be present in the VPS
production `.env`:

- `APP_ENVIRONMENT=development`
- `APP_DEBUG=true`
- `WEBAPI_SESSION_COOKIE_SECURE=false`
- `WEBAPI_ALLOWED_ORIGINS=http://localhost:5173`
- `WEBAPI_PUBLIC_URL=http://localhost:5173`
- `WEBAPI_DEV_BYPASS_AUTH` - obsolete and ignored by current code.
- `TELETHON_PHONE` after the first Telethon login has completed.
- Any token created for local testing or a development bot.

## Rotation Checklist

When preparing real production:

1. Create or choose the production Telegram bot token.
2. Rotate `MODERATOR_BOT_TOKEN` on the VPS.
3. Rotate `OPENROUTER_API_KEY` and set provider billing/usage limits.
4. Rotate PostgreSQL password if the current database was used by development.
5. Rotate `ASSISTANT_BOT_TOKEN` if the assistant bot is enabled.
6. Recreate the Telethon session only if the existing session was used for
   development or belongs to the wrong Telegram account.
7. Remove `TELETHON_PHONE` after Telethon login succeeds.
8. Set `WEBAPI_PUBLIC_URL`, `WEBAPI_ALLOWED_ORIGINS`, and
   `WEBAPI_SESSION_COOKIE_SECURE=true`.
9. Restart with `docker compose up -d --remove-orphans`.
10. Check `docker compose ps` and `docker compose logs --tail=100`.

## Safe Audit Commands

Use these commands on the VPS to inspect shape without printing secret values:

```bash
cd ~/deploy/supervisor-telegram
awk -F= '/^[A-Z][A-Z0-9_]*=/{print $1"=<redacted>"}' .env | sort
```

Run the repository audit script from a checkout to compare production `.env`
against the non-secret template:

```bash
scripts/audit_prod_env.sh ~/deploy/supervisor-telegram/.env .env.production.example
```

Check for dev-only values without revealing the whole `.env`:

```bash
grep -nE 'APP_ENVIRONMENT=development|APP_DEBUG=true|WEBAPI_SESSION_COOKIE_SECURE=false|localhost:5173|WEBAPI_DEV_BYPASS_AUTH|TELETHON_PHONE=' .env
```

Check the deploy secrets configured in GitHub:

```bash
gh secret list --repo vsem-azamat/supervisor-telegram
```
