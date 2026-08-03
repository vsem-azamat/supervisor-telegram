"""Make a chat's past visible to people who join it.

A supergroup can hide everything said before a member arrived. Telegram turns
that on by itself when a basic group is upgraded, which is how most of these
chats became supergroups, so it is usually nobody's decision — it is a default
nobody saw. The effect is a university chat where every new student opens an
empty room and asks a question that was answered last week.

    uv run python scripts/tg_prehistory.py --account work --chats scope.txt
    uv run python scripts/tg_prehistory.py --account work --chats scope.txt --apply

Without ``--apply`` it reports which chats hide their history and changes
nothing.

This one is worth thinking about before running
-----------------------------------------------
Unhiding is not a cosmetic setting. It shows every past message to everybody who
joins from now on, including people who were not in the room when those messages
were written. For a public university chat that is the point. For anything with
an expectation of privacy it is not, and the plan output is there so the list can
be read before the change is made rather than after.

It is reversible — the same call turns it back on — but what a new member read in
between cannot be unread.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tg_accounts import SESSIONS_DIR, api_credentials, session_path  # noqa: E402
from tg_promote import Journal, read_scope  # noqa: E402

if TYPE_CHECKING:
    from telethon import TelegramClient

MIN_DELAY = 2.0
MAX_DELAY = 5.0


def _client(account: str, directory: Path) -> TelegramClient:
    from telethon import TelegramClient

    api_id, api_hash = api_credentials()
    path = session_path(account, directory=directory)
    if not path.exists():
        raise SystemExit(f"no session for {account!r} at {path}")
    return TelegramClient(str(path.with_suffix("")), api_id, api_hash)


async def hides_history(client: TelegramClient, chat_id: int) -> bool | None:
    """Whether this chat hides its past. None when the question does not apply.

    Only supergroups and channels have the setting; a basic group has always
    shown its history to whoever is in it.
    """
    from telethon.tl import functions
    from telethon.tl.types import Channel

    entity = await client.get_entity(chat_id)
    if not isinstance(entity, Channel):
        return None
    full = await client(functions.channels.GetFullChannelRequest(channel=entity))
    return bool(full.full_chat.hidden_prehistory)


async def reveal(client: TelegramClient, chat_id: int) -> None:
    from telethon.tl import functions

    entity = await client.get_entity(chat_id)
    # `enabled` is whether the history stays hidden, so revealing it is False.
    await client(functions.channels.TogglePreHistoryHiddenRequest(channel=entity, enabled=False))


async def run(
    *,
    account: str,
    scope: list[Any],
    directory: Path,
    journal_path: Path | None,
    apply: bool,
    min_delay: float,
    max_delay: float,
) -> int:
    from telethon.errors import FloodWaitError

    client = _client(account, directory)
    await client.start()  # type: ignore[func-returns-value]
    journal = Journal(journal_path)

    me = await client.get_me()
    print(f"acting as {me.username or me.first_name} (id {me.id})")
    print("mode:   " + ("APPLY" if apply else "plan only (pass --apply to act)"))
    print()

    revealed = visible = failed = 0
    for entry in scope:
        label = f"{entry.chat_id:>15} {entry.title[:36]:<38}"
        if journal.already(entry.chat_id):
            print(f"{label} done earlier")
            continue

        try:
            hidden = await hides_history(client, entry.chat_id)
        except Exception as err:  # noqa: BLE001 — one unreadable chat must not end the run
            print(f"{label} cannot read: {type(err).__name__}")
            failed += 1
            continue

        if hidden is None:
            print(f"{label} basic group — history was never hidden")
            continue
        if not hidden:
            journal.record(entry.chat_id, ok=True, detail="already visible")
            print(f"{label} already visible")
            visible += 1
            continue
        if not apply:
            print(f"{label} HIDDEN — would reveal")
            continue

        try:
            await reveal(client, entry.chat_id)
        except FloodWaitError as err:
            journal.record(entry.chat_id, ok=False, detail=f"flood_wait {err.seconds}s")
            print(f"{label} flood wait {err.seconds}s — stopping. Resume after that.")
            failed += 1
            break
        except Exception as err:  # noqa: BLE001
            journal.record(entry.chat_id, ok=False, detail=f"{type(err).__name__}: {err}")
            print(f"{label} failed: {type(err).__name__}")
            failed += 1
            continue

        journal.record(entry.chat_id, ok=True, detail="revealed")
        revealed += 1
        print(f"{label} history now visible")
        await asyncio.sleep(random.uniform(min_delay, max_delay))  # noqa: S311 — pacing, not cryptography

    await client.disconnect()  # type: ignore[func-returns-value]
    print(f"\nrevealed {revealed}, already visible {visible}, failed {failed}")
    if not apply:
        print("nothing was changed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", default="work")
    parser.add_argument("--chats", type=Path, required=True, help="file of chat ids, one per line")
    parser.add_argument("--sessions-dir", type=Path, default=SESSIONS_DIR)
    parser.add_argument("--journal", type=Path, help="JSONL file recording progress, so a run can resume")
    parser.add_argument("--min-delay", type=float, default=MIN_DELAY)
    parser.add_argument("--max-delay", type=float, default=MAX_DELAY)
    parser.add_argument("--apply", action="store_true", help="actually reveal; without it nothing changes")
    args = parser.parse_args()

    return asyncio.run(
        run(
            account=args.account,
            scope=read_scope(args.chats),
            directory=args.sessions_dir,
            journal_path=args.journal,
            apply=args.apply,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
