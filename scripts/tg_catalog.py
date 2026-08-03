"""Fill in what the public catalogue needs: a link, and a university above it.

Forty-five chats exist and the catalogue listed nine, because `chats` carried
neither. Two subcommands, each of which reports what it would do and changes
nothing until ``--apply``.

    uv run python scripts/tg_catalog.py links --account work
    uv run python scripts/tg_catalog.py links --account work --apply

    uv run python scripts/tg_catalog.py parents
    uv run python scripts/tg_catalog.py parents --apply

links
-----
Reads each chat's ``@username`` through Telegram and stores ``t.me/<username>``.
Only usernames — a public chat already advertises one, and publishing it repeats
a decision its owner has already made.

It deliberately does **not** export invite links for the chats that have no
username. That would be this script deciding to publish a private group, and an
exported link is a durable thing: it keeps working after the run, for whoever
ends up holding it. Those chats stay out of the catalogue until somebody sets a
link on purpose.

parents
-------
Guesses the university from the title — ``ČVUT FIT`` under ``ČVUT | ЧВУТ`` — and
never overwrites a parent that is already set. Purely a naming argument, so no
Telegram call is involved and nothing here is irreversible.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tg_accounts import SESSIONS_DIR, api_credentials, session_path  # noqa: E402

if TYPE_CHECKING:
    from telethon import TelegramClient

MIN_DELAY = 0.4
MAX_DELAY = 1.2

# Title prefix → the title of the chat it belongs under. Order matters: the
# first match wins, so a longer prefix has to come before a shorter one that
# would also match it.
FAMILIES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^ČVUT\b", re.IGNORECASE), "ČVUT | ЧВУТ"),
    (re.compile(r"^VŠCHT\b", re.IGNORECASE), "VŠCHT"),
    (re.compile(r"^VUT\b", re.IGNORECASE), "VUT"),
    (re.compile(r"^MUNI[:\s]", re.IGNORECASE), "Masarykova univerzita"),
    (re.compile(r"^Matfyz\b", re.IGNORECASE), "Karlova univerzita | Карлов университет"),
]


def _database_url() -> str:
    """The same database the application uses, read the same way."""
    from app.core.config import settings

    return settings.database.url


def _engine() -> Any:
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(_database_url())


def _client(account: str, directory: Path) -> TelegramClient:
    from telethon import TelegramClient

    api_id, api_hash = api_credentials()
    path = session_path(account, directory=directory)
    if not path.exists():
        raise SystemExit(f"no session for {account!r} at {path}")
    return TelegramClient(str(path.with_suffix("")), api_id, api_hash)


async def _chats(engine: Any) -> list[Any]:
    from app.db.models import Chat
    from sqlalchemy import select

    async with engine.connect() as conn:
        rows = await conn.execute(
            select(Chat.id, Chat.title, Chat.public_link, Chat.parent_chat_id).order_by(Chat.title)
        )
        return list(rows.all())


# ── links ──────────────────────────────────────────────────────────────────


async def run_links(*, account: str, directory: Path, apply: bool) -> int:
    import random

    from app.db.models import Chat
    from sqlalchemy import update

    engine = _engine()
    chats = await _chats(engine)

    client = _client(account, directory)
    await client.start()  # type: ignore[func-returns-value]
    me = await client.get_me()
    print(f"acting as {me.username or me.first_name} (id {me.id})")
    print("mode:   " + ("APPLY" if apply else "plan only (pass --apply to act)"))
    print()

    found = unchanged = private = failed = 0
    updates: list[tuple[int, str]] = []

    for row in chats:
        label = f"{row.id:>15} {(row.title or '')[:38]:<40}"
        try:
            entity = await client.get_entity(row.id)
        except Exception as err:  # noqa: BLE001 — one unreadable chat must not end the run
            print(f"{label} cannot read: {type(err).__name__}")
            failed += 1
            continue

        username = getattr(entity, "username", None)
        if not username:
            print(f"{label} no username — stays out of the catalogue")
            private += 1
            continue

        link = f"https://t.me/{username}"
        if row.public_link == link:
            print(f"{label} already {link}")
            unchanged += 1
            continue

        print(f"{label} {'set' if apply else 'would set'} {link}")
        updates.append((row.id, link))
        found += 1
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))  # noqa: S311 — pacing, not cryptography

    if apply and updates:
        async with engine.begin() as conn:
            for chat_id, link in updates:
                await conn.execute(update(Chat).where(Chat.id == chat_id).values(public_link=link))

    await client.disconnect()  # type: ignore[func-returns-value]
    await engine.dispose()

    print(f"\nlinked {found}, already linked {unchanged}, no username {private}, unreadable {failed}")
    if not apply:
        print("nothing was changed.")
    return 1 if failed else 0


# ── parents ────────────────────────────────────────────────────────────────


def family_of(title: str) -> str | None:
    for pattern, parent_title in FAMILIES:
        if pattern.search(title):
            return parent_title
    return None


async def run_parents(*, apply: bool) -> int:
    from app.db.models import Chat
    from sqlalchemy import update

    engine = _engine()
    chats = await _chats(engine)
    by_title = {row.title: row.id for row in chats if row.title}

    print("mode:   " + ("APPLY" if apply else "plan only (pass --apply to act)"))
    print()

    placed = kept = orphan = 0
    updates: list[tuple[int, int]] = []

    for row in chats:
        label = f"{row.id:>15} {(row.title or '')[:38]:<40}"
        if not row.title:
            continue
        if row.parent_chat_id is not None:
            kept += 1
            continue

        parent_title = family_of(row.title)
        parent_id = by_title.get(parent_title) if parent_title else None
        if parent_id is None or parent_id == row.id:
            # The family head itself, or a chat that belongs to nobody. Both are
            # fine: a top-level chat simply has no university above it.
            print(f"{label} top level")
            orphan += 1
            continue

        print(f"{label} {'under' if apply else 'would go under'} {parent_title}")
        updates.append((row.id, parent_id))
        placed += 1

    if apply and updates:
        async with engine.begin() as conn:
            for chat_id, parent_id in updates:
                await conn.execute(update(Chat).where(Chat.id == chat_id).values(parent_chat_id=parent_id))

    await engine.dispose()

    print(f"\nplaced {placed}, already placed {kept}, top level {orphan}")
    if not apply:
        print("nothing was changed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    links = sub.add_parser("links", help="store t.me/<username> for every chat that advertises one")
    links.add_argument("--account", default="work")
    links.add_argument("--sessions-dir", type=Path, default=SESSIONS_DIR)
    links.add_argument("--apply", action="store_true", help="actually write; without it nothing changes")

    parents = sub.add_parser("parents", help="put each faculty chat under its university")
    parents.add_argument("--apply", action="store_true", help="actually write; without it nothing changes")

    args = parser.parse_args()

    if not os.environ.get("DB_HOST"):
        print("DB_HOST is not set — point this at a database first.", file=sys.stderr)
        return 2

    if args.command == "links":
        return asyncio.run(run_links(account=args.account, directory=args.sessions_dir, apply=args.apply))
    return asyncio.run(run_parents(apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
