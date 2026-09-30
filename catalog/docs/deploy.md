# Deployment

> **In transition (30 September 2026).** The code is in `supervisor-telegram`
> now, but production still runs the stack below, deployed from the
> `teachers-catalog` repository, until the deploy moves into this
> repository's own workflow. Until then a change here reaches production only
> once that move lands.

Production runs on a shared VPS alongside other projects. The shape follows the
one already in use there, so the two behave the same way when something breaks.

```
client
  → Cloudflare (TLS, proxied A record)
  → shared Edge Caddy on the host, ports 80/443
  → 127.0.0.1:<project port>
  → this project's Caddy
  → FastAPI (/api/v1, /healthz), or 301 to APP_URL for anything else
```

The Mini App is not here: it is supervisor-telegram's `web/`, at `APP_URL`,
and that host's router proxies `/api/v1/*` and `/healthz` to this one, because
since 20 July 2026 Telegram only allows Mini App API calls from the app's own
origin. See docs/architecture.md, «The app lives elsewhere».

## How a deployment happens

Nothing is built on the server.

1. Push to `main` runs **CI**. Deployment is a separate workflow triggered by
   CI *succeeding* — so only a commit that passed tests can ship.
2. **Deploy** builds the API image and pushes it to GHCR under
   `prod-<short-sha>` and `prod-latest`. The immutable tag is what gets
   deployed; `prod-latest` exists only for humans reading the registry.
3. It copies the compose file, the Caddyfile, the route script and a freshly
   generated mode-0600 `.env` to the server over SSH.
4. On the server: `docker compose run --rm migrate` — Alembic runs to
   completion before anything serves traffic, and a failed migration stops the
   deployment with a readable error instead of crash-looping the API.
5. `docker compose up -d --wait` — every service must report healthy.
6. The published port is asserted to be `127.0.0.1:<port>` and nothing else.
7. The hostname is registered with the shared Edge Caddy, under a marked block
   this project owns, behind a host-wide lock, validated before reload and
   rolled back on failure.
8. Public smoke tests.

If anything fails before step 6, the previous `.env`, compose file and
Caddyfile are restored together and the previous stack is brought back up.
If any of them cannot be copied back, nothing is restarted and the containers
are left in whatever state the failure put them. The log names the files and
the private directory on the server where the previous release's copies are
kept; copy them back, or deploy forward, before anything restarts.
The new compose file and Caddyfile arrive staged beside the live ones, so
until then the previous release is untouched. After step 6 the release is committed;
recovering from a bad release is `Rollback production`.

### Reference data does not ship with the code

Step 4 runs Alembic and nothing else. `students_cz.db.seed` — subjects,
institutions, service types, languages — is a development and CI convenience;
production was seeded once and is never re-seeded.

So a change to `seed.py` alone reaches every fresh checkout and never reaches
the catalog people are using. Anything that has to take effect in production
needs a migration carrying the same change, and the migration writes the
values out rather than importing the constant: a migration describes the
database at one moment, and one that follows a constant changes meaning the
next time that constant does.

## Rolling back

Run the **Rollback production** workflow with a tag such as `prod-1a2b3c4`. It
rewrites `IMAGE_TAG` in the server's `.env`, pulls, and restarts. It does not
build and it does not migrate — reversing a schema change is a separate,
riskier decision that should be made deliberately.

Only per-commit tags are accepted. `prod-latest` would roll *forward* to
whatever shipped last, which is the opposite of what the button says.

It cannot reach past the rename. Images built before the project became
`students-cz` were pushed as `konnekt-api` and `konnekt-web`, and the compose
file asks for the current names, so a tag from before it will pull nothing.
Anything from the first deployment after the rename onwards rolls back
normally.

## The names that stay

The compose project is `students-cz`; the volumes it uses are not. They are
pinned by name to `konnekt_postgres-data`, `konnekt_caddy-data` and
`konnekt_caddy-config`, because a compose volume is `<project>_<name>` and
renaming the project would otherwise hand postgres an empty disk and make Caddy
re-issue every certificate against Let's Encrypt's rate limits. The old name in
there is where the data is, not a preference.

The Postgres role and database are whatever the server's `.env` says, and that
file is not in this repository. Renaming them is a dump and a restore for
something nobody ever sees, so it has not been done.

The first deployment after the rename stops the old `konnekt` project before
starting the new one — otherwise both run, and the new Caddy loses the race for
the published port after the migrations have already gone through. That step is
guarded and can be deleted once no server has such a project left.

## One-time setup

None of this is in the repository, because the repository is public.

### 1. DNS

In Cloudflare, on the zone: an **A** record for the chosen subdomain, pointing
at the same origin as the existing project, **proxied** (orange cloud), TTL
auto. Nothing in CI provisions DNS.

### 2. A deploy identity on the server

Prefer a dedicated key over reusing a personal one. Membership of the `docker`
group is effectively root, so this identity should be treated as such.

```sh
ssh-keygen -t ed25519 -C 'github-actions students-cz deploy' -f students-cz_deploy
ssh-copy-id -i students-cz_deploy.pub <user>@<host>
ssh-keyscan -t ed25519 <host>          # for DEPLOY_KNOWN_HOSTS
```

### 3. Repository secrets

| Secret | What it is |
| --- | --- |
| `DEPLOY_HOST` | Server address. Never commit it — the repository is public. |
| `DEPLOY_USER` | SSH user. |
| `DEPLOY_DIR` | Absolute path for this project's directory on the server. |
| `DEPLOY_SSH_KEY` | Private key from step 2. |
| `DEPLOY_KNOWN_HOSTS` | Output of `ssh-keyscan`. Deliberately not fetched at deploy time — accepting whatever key answers would defeat the point. |
| `EDGE_CADDY_DIR` | Directory of the shared edge project. |
| `EDGE_CADDY_COMPOSE_FILE` | Its compose file. |
| `EDGE_CADDYFILE` | Path on the host to the shared Caddyfile. |
| `BOT_TOKEN` | The Konnekt moderator bot's token, the same value as `MODERATOR_BOT_TOKEN` in `supervisor-telegram`. See the warning below. |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24`. |

### 4. Repository variables

| Variable | Value |
| --- | --- |
| `PUBLIC_HOST` | `https://<subdomain>` — scheme and host, no path, no trailing slash. |
| `PUBLIC_PORT` | A loopback port not used by another project on the host. |
| `APP_URL` | `https://<host>` of the Mini App (supervisor-telegram). Every path here other than `/api/v1/*` and `/healthz` answers 301 to it, and the bot's buttons open it. Required, checked like `PUBLIC_HOST`, and never equal to it. Set it before any deploy of a release that reads it: without it the deploy refuses. |
| `EDGE_CADDY_SERVICE` | Service name of the edge Caddy in its compose file. |
| `EDGE_CADDY_CONFIG_PATH` | Path to the Caddyfile *inside* that container. |
| `POSTGRES_DB`, `POSTGRES_USER` | Required, and checked before anything ships. No default on purpose: they name a role and a database that already exist inside a volume, and a wrong guess does not create them — the entrypoint skips `initdb` on a cluster that is not empty. The password is a secret, above. |
| `INIT_DATA_MAX_AGE_SECONDS` | Optional; defaults to 86400. |
| `LOG_LEVEL` | Optional; defaults to `INFO`. One of DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| `BACKUP_HOUR_UTC`, `BACKUP_RETENTION_DAYS` | Optional; default 3 and 14. |
| `ADS_CONTACT` | Optional. The Telegram username, without `@`, that the ads page tells a business to write to. Unset means the page has no contact button. |
| `ADMIN_TG_IDS` | Optional. Comma-separated Telegram ids of the console's operators, the same as `ADMIN_SUPER_ADMINS` in `supervisor-telegram`. Unset means nobody reads the catalog or runs partner cards in the console. See docs/architecture.md, «The operator reads the catalog and runs the partner cards». |
| `OWNER_TG_ID` | Optional. Telegram id of whoever runs this, to be told when a profile or a request appears. Unset means no ping. Should be one of `ADMIN_TG_IDS`: the ping's button opens the console. A numeric id, not a handle — the bot needs a chat it can open, and it can only open one with somebody who has started the moderator bot. |

### 5. In @BotFather

Nothing. The Mini App URL, the menu button, the command list and the greeting
belong to the moderator bot, and `supervisor-telegram` sets them.

## Moving onto the moderator's token, once

The catalog's own bot is `@student_cz_bot`, and its token is in `BOT_TOKEN`
until step 3. Each step assumes the one before it. Steps 2 to 4 run back to
back: in between, the old bot has no menu and the moderator bot has no door
to the catalog yet.

1. Deploy the release that stops receiving updates, still on the old token.
2. Run **Retire the old bot** (Actions → workflow dispatch). It reads the old
   token from `BOT_TOKEN`, checks with `getMe` that it really is
   `@student_cz_bot`, and refuses to touch any other bot. Then it deletes the
   old bot's webhook, resets its menu button, clears its command list and
   says in its description how to reach the catalog through
   `@konnekt_moder_bot`. After step 3 the guard makes it refuse.
3. Replace the `BOT_TOKEN` secret with the moderator bot's token, the same
   value as `MODERATOR_BOT_TOKEN` in `supervisor-telegram`, and re-run the
   deploy.
4. `supervisor-telegram`'s `/start` offers «🎓 Помощь с учёбой», which opens
   the app at `APP_URL`.
5. In @BotFather, remove `@student_cz_bot`'s Main Mini App URL. The Bot API
   cannot do this one.
6. Check that Telegram sends `allows_write_to_pm` on this launch. Set your
   own row's `bot_can_message` to false in `users`, open the catalog from
   `@konnekt_moder_bot` with «🎓 Помощь с учёбой», and read the row again. It
   has to be true. If it stays false, nobody new can be notified: stop and
   look at the `initData` the app sends before going further.

Old `web_app` buttons already sitting in people's chats with `@student_cz_bot`
open the app with initData signed by the old token. After step 3 the API
refuses it, and nothing can repair a message that was already sent.

**`rollback.yml` cannot return to a release before this one, on purpose.** Releases before
this one register a webhook and refuse to start without `WEBHOOK_SECRET`.
Compose still passes `WEBHOOK_SECRET` for one release, so a failed step-1
deploy can restore the previous release and come back up. `rollback.yml`
keeps the new `.env`, which has no `WEBHOOK_SECRET`, so an old image crashes
at start. Keep it that way once `BOT_TOKEN` is the moderator's: an old image
on that token would set a webhook every minute and break the moderator bot's
polling. Never put `WEBHOOK_SECRET` back.

## Two ways to break production

**Asking for updates with this token.** The token is the moderator bot's, and
`supervisor-telegram` receives its updates by polling. Telegram gives a token
one consumer. A `setWebhook` from anywhere stops that polling, and a second
`getUpdates` makes the two pollers fail each other with `409 Conflict`. The API
never does either. The legacy bot in `bot/` polls, so never run it with this
token. See [legacy-bot.md](legacy-bot.md).

**More than one Uvicorn worker.** The API holds no bot state, so a second
worker would not break Telegram. It would still double the database budget:
the connection pool is per process, and the `--workers 1` pin in the
Dockerfile is what makes `db_pool_size` and `db_max_overflow` the whole budget
against Postgres — 15 connections by default. Raising the worker count
multiplies it.

## Backups

A sidecar runs `pg_dump --format=custom` daily at `BACKUP_HOUR_UTC` into
`<DEPLOY_DIR>/data/backups`, keeping `BACKUP_RETENTION_DAYS`. Dumps are written
to a `.part` file and renamed only on success, so a partial file is never
mistaken for a usable backup.

They sit on the same disk as the database, which protects against a bad
migration and not against losing the machine. Copying them off the host is not
set up yet.

To restore:

```sh
docker compose exec -T postgres sh -c 'pg_restore --clean --if-exists \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < data/backups/<file>.dump
```

Test that on a copy before you need it in anger.

## Checking on it

```sh
curl https://<host>/healthz                      # API and database
curl -sI https://<host>/                         # 301 to APP_URL
docker compose -f <DEPLOY_DIR>/docker-compose.yml ps
docker compose -f <DEPLOY_DIR>/docker-compose.yml logs -f api
```

Caddy is recreated whenever the Caddyfile changes: the deploy puts the file's
hash in `CADDYFILE_SHA`, which the caddy service carries, so a release that
changes only the Caddyfile still takes effect, and so does its restore.

`/healthz` answers `status`, `database` and `uptime_seconds`. It says nothing
about Telegram: this process holds no webhook, so there is nothing of its own
there to report. Whether the bot hears people is `supervisor-telegram`'s
health check.
