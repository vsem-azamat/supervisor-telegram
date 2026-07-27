# Production Credentials

Production configuration lives in **GitHub**, as repository secrets and
variables. The VPS holds no copy: the deploy workflow forwards everything over
SSH with the deploy command, so a value changes in one place and reaches the
host on the next deploy.

Nothing here belongs in commits, issues, agent transcripts, screenshots, or a
file on the server.

## Secrets

Credentials. Once set, GitHub will not show them again — rotate rather than
recover.

| Secret | What it is |
| --- | --- |
| `DB_PASSWORD` | PostgreSQL password |
| `MODERATOR_BOT_TOKEN` | Bot token from BotFather |
| `OPENROUTER_API_KEY` | Model access for moderation and content |
| `BRAVE_API_KEY` | Search, used by content discovery |
| `TELETHON_API_HASH` | Half of the userbot's API credentials |
| `MCP_TOKEN` | Bearer token for the control plane |
| `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` | Deploy target and key |

`MCP_TOKEN` is the entire protection on a plane that can mute, unmute, unban and
read chat history through a user session. Generate with `openssl rand -hex 32`.

The Telethon **session file** is not a GitHub secret — it is a file on the host,
mounted into the bot container from
`~/deploy/supervisor-telegram/moderator_userbot.session`. It authenticates a
real Telegram account and grants far more than any bot token; treat it as the
most sensitive artefact in the deployment.

## Variables

Everything else that differs between environments. Readable by anyone with
repository access, so nothing sensitive goes here.

| Variable | Notes |
| --- | --- |
| `DB_USER`, `DB_HOST`, `DB_PORT`, `DB_NAME` | |
| `ADMIN_SUPER_ADMINS` | Comma-separated Telegram IDs |
| `ADMIN_REPORT_CHAT_ID` | |
| `APP_ENVIRONMENT`, `LOG_LEVEL` | |
| `MODERATION_ENABLED`, `CHANNEL_ENABLED` | Both require `OPENROUTER_API_KEY` |
| `TELETHON_ENABLED`, `TELETHON_API_ID`, `TELETHON_SESSION_NAME` | |
| `WEBAPI_AUTH_MODE`, `WEBAPI_PUBLIC_URL`, `WEBAPI_ALLOWED_ORIGINS` | |
| `WEBAPI_SESSION_COOKIE_SECURE` | `true` in production |
| `SPONSORED_ADS_ENABLED`, `SPONSORED_ADS_MODERATOR_CHAT_ID`, `SPONSORED_ADS_SALES_CONTACT` | |
| `MCP_ENABLED`, `MCP_PATH`, `MCP_PORT`, `MCP_INITIATOR_ID` | |
| `WEBUI_PORT` | Loopback-only host port for the edge proxy |

Anything absent falls back to the default in `app/core/config.py`. The list is
deliberately not a second copy of every setting — models, thresholds and
intervals are code, and changing them should be a reviewed change rather than a
click.

## What the deploy checks

Before anything reaches the VPS the workflow fails on:

- any of `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `MODERATOR_BOT_TOKEN`,
  `ADMIN_SUPER_ADMINS` being empty — these have no defaults, and containers
  crash on boot without them;
- `MCP_ENABLED=true` without `MCP_TOKEN`, or with `MCP_INITIATOR_ID` unset — the
  plane would fail closed, which looks like a dead endpoint rather than a
  misconfiguration;
- `MODERATION_ENABLED` or `CHANNEL_ENABLED` without `OPENROUTER_API_KEY`.

A test pins the forwarded list against `docker-compose.yaml`, so a setting added
to one and not the other fails in CI rather than in production.

## Seeding and changing values

`scripts/env_to_github.sh` loads an env file into this repository's secrets and
variables — the old VPS `.env` for the first migration, or any file afterwards.
It prints a plan and writes nothing until `--apply`, never prints a value, and
names anything it ignored so a setting that is about to stop taking effect is
visible rather than silently dropped.

```bash
scripts/env_to_github.sh ~/deploy/supervisor-telegram/.env
scripts/env_to_github.sh ~/deploy/supervisor-telegram/.env --apply
```

Run it from a machine that can read the file. Once the values are in GitHub,
delete the `.env` from the VPS: it is no longer read, and a stale copy of
production credentials is worth less than nothing.

## Rotation

1. Generate the new value.
2. Update the secret or variable in GitHub.
3. Re-run the deploy workflow — the new value reaches the host with the command.
4. Revoke the old value at its source: BotFather for bot tokens, the provider
   console for API keys, `ALTER ROLE` for the database.
5. Confirm the containers came up: `docker compose ps` and recent logs.

Rotating `MCP_TOKEN` also means updating whatever client holds it.

## If a value leaks

Rotate first, investigate after. For `MCP_TOKEN`, check `pending_actions` for
proposals nobody made — the plane cannot ban on its own, so a leak shows up as
requests awaiting confirmation rather than as damage already done.

For the Telethon session, terminate it from Telegram's own active-sessions list.
Rotating API credentials does not invalidate an already-authorised session.
