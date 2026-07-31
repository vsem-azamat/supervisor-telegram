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
| `DB_PASSWORD` | PostgreSQL password. The database runs beside this stack rather than in it, so this is the password that database already has — see [The Database](database.md). |
| `MODERATOR_BOT_TOKEN` | Bot token from BotFather |
| `TELETHON_API_ID`, `TELETHON_API_HASH` | The userbot's API credentials. Together they reach a real account, so both are secrets — half a pair in `vars` protects nothing. |
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
| `ADMIN_SUPER_ADMINS` | Comma-separated Telegram IDs |
| `ADMIN_REPORT_CHAT_ID` | Defaults to the first super admin |
| `WEBAPI_PUBLIC_URL` | Also becomes the allowed CORS origin |

## Features switch themselves on

Nothing here is switched on by a flag. A feature is on when it is configured
and off otherwise:

| Feature | On when |
| --- | --- |
| Telethon userbot | `TELETHON_API_ID` and `TELETHON_API_HASH` are both set |
| MCP control plane | `MCP_TOKEN` is set |

A separate flag could disagree with the configuration it gates, and only ever in
the direction that fails quietly: `TELETHON_ENABLED=true` with no credentials
produced a userbot that started, failed, and said nothing.

Some values are fixed in `docker-compose.yaml` rather than configured, because
they cannot differ without breaking something. The MCP port and path are pinned
to the container port mapping; the Telethon session name is pinned to the volume
mount, and a mismatch there makes Telethon start an unauthorised session instead
of failing.

Anything absent falls back to the default in `app/core/config.py`. The list is
deliberately not a second copy of every setting — thresholds and intervals are
code, and changing them should be a reviewed change rather than a click.

## What the deploy checks

Before anything reaches the VPS the workflow fails on:

- any of `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `MODERATOR_BOT_TOKEN`,
  `ADMIN_SUPER_ADMINS` being empty — these have no defaults, and containers
  crash on boot without them;
- one half of the Telethon credential pair without the other, which activates
  nothing and looks like a working deploy with a userbot that never connects;

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
