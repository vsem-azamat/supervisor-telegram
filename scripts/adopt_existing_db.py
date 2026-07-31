"""Bring an existing database under the squashed migration history.

The repository's thirty-six migrations were replaced by one initial schema, so a
database created by the old history holds a revision that no longer exists and
`alembic upgrade head` cannot start from it.

Three steps, in this order:

1. create the tables the initial schema adds and this database does not have,
   using the same definitions the migration would have used;
2. stamp the initial revision, which is now a true statement about the schema;
3. upgrade normally — everything after the squash applies as usual.

Run once, against a database that predates the squash.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import models as _models  # noqa: F401  # register the ORM models
from app.db.base import Base

INITIAL_REVISION = "fbeb70328d81"

# Everything the squashed initial migration creates. Tables added after it are
# not listed: those are what `alembic upgrade` is for.
INITIAL_TABLES = {
    "admin_magic_links",
    "admin_sessions",
    "admins",
    "chat_links",
    "chat_member_snapshots",
    "chats",
    "join_checks",
    "messages",
    "pending_actions",
    "spam_pings",
    "users",
}


async def missing_initial_tables(url: str) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            present = set(await conn.run_sync(lambda sync: inspect(sync).get_table_names()))
    finally:
        await engine.dispose()
    return sorted(INITIAL_TABLES - present)


async def create_missing(url: str, names: list[str]) -> None:
    engine = create_async_engine(url)
    tables = [Base.metadata.tables[name] for name in names]
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
    finally:
        await engine.dispose()


async def main() -> int:
    from app.core.config import settings

    url = settings.database.url
    missing = await missing_initial_tables(url)

    if not missing:
        print("nothing missing from the initial schema.")
    else:
        print("creating:", ", ".join(missing))
        await create_missing(url, missing)
        print("created.")

    print(f"\nnow run:\n  alembic stamp {INITIAL_REVISION}\n  alembic upgrade head\n  alembic check")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
