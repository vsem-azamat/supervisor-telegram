# Moving the production data onto the stack's own database

Until this change Postgres was not part of the compose project. The bot reached
it over `DB_HOST` and the repository knew nothing about where it ran. The stack
now brings up its own `db` service on a `pgdata` volume, which means the first
deploy **starts an empty database beside the old one**. Nothing is dropped,
nothing is overwritten — the old server keeps running and the bot simply stops
looking at it. Until the rows are carried across, the bot behaves like a fresh
install: no chats, no blacklist, no admins.

## What has to happen once

1. Deploy, so the new database exists and the migrations have run.
2. Copy the rows across with `scripts/import_legacy_db.py`.
3. Check the blacklist and the chat list in the admin UI.
4. Only then retire the old server.

## Why not `pg_dump`

A data-only dump names every column it finds. The old schema still has columns
and whole tables this repository dropped — the content pipeline's, the cost
ledger's, the pgvector embedding — so restoring one into the current schema
fails on the first column that no longer exists, and the failure comes late,
after a long restore.

`scripts/import_legacy_db.py` copies table by table using the columns the two
schemas agree on, and prints what it left behind on each one:

```
chats        2 rows  (not carried over: legacy_channel_id; left at default: photo_file_id)
```

Read that line. "Not carried over" is a column the old database had and this one
does not — expected for anything belonging to a removed feature, worth a second
look otherwise. "Left at default" is a column this schema added since.

## Running it

From a machine that can reach both databases, with the same environment the bot
runs under — the target is whatever the configuration points at, never a flag:

```bash
# reads both schemas, counts rows, writes nothing
uv run python scripts/import_legacy_db.py --source postgresql://user:pass@old-host:5432/konnekt

# same, but writing
uv run python scripts/import_legacy_db.py --source postgresql://user:pass@old-host:5432/konnekt --apply
```

On the VPS, the new database is not published outside the compose network, so
run it from inside the stack:

```bash
docker compose exec bot \
  uv run python scripts/import_legacy_db.py --source postgresql://user:pass@old-host:5432/konnekt --apply
```

Safe to repeat. Rows already present are skipped rather than duplicated, so an
import that dies halfway can simply be run again. Afterwards the id sequences
are moved past the imported rows — without that the next insert would be handed
an id the old data already uses.

## Afterwards

The `chats` table is what the moderator bot works from; if it is empty the bot
manages nothing. Confirm in the admin UI that the chat list and the blacklist
look like they did, then stop the old Postgres. Keep its volume until you are
sure — it is the only copy of everything this import deliberately left behind.
