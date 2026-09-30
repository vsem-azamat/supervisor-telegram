# The database

It is not part of this stack. It is a database on the shared PostgreSQL
server, another machine than the one this stack runs on, and it holds the
production data, so `docker-compose.yaml` starts no `db` service and
where the database lives is deployment configuration: `DB_HOST`, `DB_PORT`,
`DB_USER`, `DB_NAME` come from GitHub variables and `DB_PASSWORD` from a secret.

That was a choice, made to keep one PostgreSQL server for several projects,
and it costs one thing worth knowing about — see *Exposure*.

## The database predates the migration squash

Thirty-six migrations were replaced by a single initial schema. A database built
by the old history holds a revision number this repository no longer contains,
so `alembic upgrade head` cannot start from it: it fails with *Can't locate
revision*. Adopting such a database is a one-time sequence:

```bash
uv run python scripts/adopt_existing_db.py   # creates the tables the squash adds
uv run alembic stamp fbeb70328d81 --purge    # --purge: the recorded revision is gone
uv run alembic upgrade head
uv run alembic check                         # must say: no new upgrade operations
```

`--purge` is what makes the stamp possible at all. Without it Alembic tries to
resolve the revision already in the table before writing the new one, and that is
exactly the revision that no longer exists.

This was run once, on 2026-07-31, against the production database. It is
recorded here because the same steps apply to any other database created before
the squash, and because *why* a stamp was acceptable needs stating: production
matched the squashed schema for every table it had, and the two it lacked were
created first, so the stamp was a true statement rather than a promise.

Two follow-ups came out of it, both in `c8d5e2f47a19`: five columns the models
declare NOT NULL were nullable in production (no row violated them), and two
primary keys were `bigint` there against `Integer` in the models — production
was right, and the models moved.

## Tables this repository does not own

The production database still holds tables from features that have left: the
content pipeline's, the moderation agent's, the cost ledger's. They are not
dropped — they hold data that may still be wanted when that work moves to its
own repository — and `alembic/env.py` filters them out of autogenerate, so
`alembic revision --autogenerate` will not propose deleting them.

## Exposure

The database server listens on its public interface, behind a source allowlist
and a password. Keeping that allowlist to the hosts that need it is the
database server's job; nothing in this repository can do it.

If it is ever moved inside the compose network, the data has to move with it —
`git log` has the import that does this, removed once this route was chosen.

## Backups

The shared database server's own backup jobs do not cover this database. The
stack's `db-backup` service dumps it daily at 02:00 UTC with `pg_dump
--format=custom`, using the bot's own connection settings, into
`~/deploy/supervisor-telegram/db-backups/` (0700) on the application host, and
keeps 30 days. That is another machine than the database's, so losing either
one leaves the other. A dump is written to a `.part` file and renamed only on
success.

To restore, into a scratch database first:

```sh
docker run --rm -i -e PGPASSWORD pgvector/pgvector:0.8.6-pg18-bookworm \
  pg_restore --no-owner --no-privileges -h <scratch host> -U <user> -d <scratch> \
  < db-backups/<file>.dump
```
