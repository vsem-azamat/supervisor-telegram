"""Copy the production data onto the database this stack now runs.

Until this branch, Postgres lived outside the compose project — the bot reached
it over ``DB_HOST`` and the repository knew nothing about it. The stack now owns
its database, so a deploy brings up an empty one beside the old server rather
than deleting anything. This carries the rows across.

Column-by-column instead of ``pg_dump``: the old schema has tables and columns
this one no longer has, and a data-only dump names every column it finds, so
restoring it into the current schema fails on the first one that is gone. Here
each table copies the columns the two schemas agree on and says what it left.

Usage::

    uv run python scripts/import_legacy_db.py --source postgresql://user:pass@host:5432/db
    uv run python scripts/import_legacy_db.py --source ... --apply

``LEGACY_DB_URL`` is read when ``--source`` is absent, which is how it runs
unattended: a DSN passed as an argument is visible in the host's process list.

Without ``--apply`` nothing is written: it reads both schemas, counts the rows
and prints what a run would do. Safe to repeat — rows already present are left
alone rather than duplicated, so an interrupted import can simply be run again.

Point ``--source`` at the *old* database. The target is whatever this process's
configuration points at, so run it with the same environment the bot uses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import TYPE_CHECKING, Any

from app.db import models as _models  # noqa: F401  # register the ORM models
from app.db.base import Base
from sqlalchemy import Integer, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncEngine

BATCH = 500


def _async_url(url: str) -> str:
    """Accept the psql-style URL an operator has to hand."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _read_columns(sync_conn: Any, table: str) -> set[str]:
    inspector = inspect(sync_conn)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


async def _columns(engine: AsyncEngine, table: str) -> set[str]:
    """The columns the source actually has, or an empty set if the table is gone."""
    async with engine.connect() as conn:
        return await conn.run_sync(_read_columns, table)


async def _copy(
    source: AsyncEngine,
    target: AsyncEngine,
    table: Table,
    *,
    apply: bool,
) -> tuple[int, list[str], list[str]]:
    """Copy one table. Returns rows seen, columns dropped, columns left empty."""
    available = await _columns(source, table.name)
    if not available:
        return -1, [], []

    wanted = {column.name for column in table.columns}
    shared = [column.name for column in table.columns if column.name in available]
    dropped = sorted(available - wanted)
    absent = sorted(wanted - available)

    columns = [table.c[name] for name in shared]
    async with source.connect() as conn:
        total = (await conn.execute(select(func.count()).select_from(table))).scalar_one()
        if not apply or total == 0:
            return int(total), dropped, absent

        result = await conn.stream(select(*columns).execution_options(yield_per=BATCH))
        async with target.begin() as write:
            async for partition in result.partitions(BATCH):
                rows: list[dict[str, Any]] = [dict(zip(shared, row, strict=True)) for row in partition]
                statement = pg_insert(table).values(rows)
                # A rerun after an interruption must not duplicate anything, and
                # the primary keys come from the source, not from a sequence.
                await write.execute(statement.on_conflict_do_nothing())

    return int(total), dropped, absent


async def _resync_sequences(target: AsyncEngine, tables: list[Table]) -> None:
    """Move each serial sequence past the ids that were just inserted.

    The rows carry their original primary keys, so a sequence still sitting at 1
    would hand the next insert an id that is already taken.
    """
    async with target.begin() as conn:
        for table in tables:
            for column in table.primary_key.columns:
                if not isinstance(column.type, Integer):
                    continue
                # Identifiers cannot be bound parameters, so both names are
                # interpolated — they come from this repository's own metadata,
                # never from the source database or the command line.
                await conn.execute(
                    text(
                        f"SELECT setval(seq, COALESCE((SELECT MAX({column.name}) FROM {table.name}), 1), true) "  # noqa: S608
                        f"FROM pg_get_serial_sequence('{table.name}', '{column.name}') AS seq "
                        "WHERE seq IS NOT NULL"
                    )
                )


async def run(source_url: str, *, apply: bool) -> int:
    from app.core.config import settings

    source = create_async_engine(_async_url(source_url))
    target = create_async_engine(settings.database.url)

    print(f"source: {source.url.render_as_string(hide_password=True)}")
    print(f"target: {target.url.render_as_string(hide_password=True)}")
    print("mode:   " + ("APPLY — rows will be written" if apply else "plan only (pass --apply to write)"))
    print()

    copied: list[Table] = []
    try:
        for table in Base.metadata.sorted_tables:
            total, dropped, absent = await _copy(source, target, table, apply=apply)
            if total < 0:
                print(f"  {table.name:<24} absent in source, skipped")
                continue
            copied.append(table)
            notes = []
            if dropped:
                notes.append(f"not carried over: {', '.join(dropped)}")
            if absent:
                notes.append(f"left at default: {', '.join(absent)}")
            suffix = f"  ({'; '.join(notes)})" if notes else ""
            print(f"  {table.name:<24} {total:>7} rows{suffix}")

        if apply:
            await _resync_sequences(target, copied)
            print("\nsequences moved past the imported ids.")
        else:
            print("\nnothing was written.")
    finally:
        await source.dispose()
        await target.dispose()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        default=os.environ.get("LEGACY_DB_URL", ""),
        help="DSN of the old database; defaults to LEGACY_DB_URL, which keeps it out of the process list",
    )
    parser.add_argument("--apply", action="store_true", help="actually write; without it nothing is changed")
    args = parser.parse_args()

    if not args.source:
        parser.error("pass --source or set LEGACY_DB_URL")

    return asyncio.run(run(args.source, apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
