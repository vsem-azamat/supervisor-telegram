"""Clear the pile of "someone joined", "someone left" notices out of a chat.

A quiet chat ends up reading as a membership log: dozens of Telegram's own
notices in a row, with the occasional real message lost among them. They carry
nothing anybody needs — the member list is the member list — and in a chat that
gets a message a week they are most of what is there.

    uv run python scripts/tg_tidy.py --account work --chats scope.txt
    uv run python scripts/tg_tidy.py --account work --chats scope.txt --apply

Without ``--apply`` it counts what it would remove, per chat, and removes
nothing.

What counts as a notice
-----------------------
Only Telegram's own service messages about who is in the chat: somebody was
added, joined by a link, or left. Nothing a person wrote is ever a candidate —
a service message has no text to read, which is what makes this safe to run
across chats nobody has audited.

Changes to the chat itself — a new title, a new photo — are notices too, and are
left alone unless ``--include-chat-changes`` says otherwise. They are rare, and
unlike a join they record a decision somebody made.

How far back
------------
By default the most recent few thousand messages, which in a quiet chat is its
whole life. ``--all`` walks to the beginning; in a chat with real traffic that
is a long read for very little, since the notices there are already buried.
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
MAX_DELAY = 6.0

# Telegram accepts this many ids per delete call.
BATCH = 100

# Deep enough to cover a quiet chat entirely, shallow enough not to read years
# of a busy one for the sake of notices nobody scrolls back to.
DEFAULT_LOOKBACK = 3000


def membership_actions() -> tuple[type, ...]:
    """Notices about who is in the chat.

    ``JoinedByRequest`` is the one that matters most here and the easiest to
    miss. A chat with join approval turned on — which is most of these — records
    every approved applicant that way rather than as an addition, so leaving it
    out would clear a handful of notices and leave the actual pile untouched.
    """
    from telethon.tl.types import (
        MessageActionChatAddUser,
        MessageActionChatDeleteUser,
        MessageActionChatJoinedByLink,
        MessageActionChatJoinedByRequest,
    )

    return (
        MessageActionChatAddUser,
        MessageActionChatDeleteUser,
        MessageActionChatJoinedByLink,
        MessageActionChatJoinedByRequest,
    )


def chat_change_actions() -> tuple[type, ...]:
    """Notices about the chat itself, which record a decision rather than traffic."""
    from telethon.tl.types import (
        MessageActionChatDeletePhoto,
        MessageActionChatEditPhoto,
        MessageActionChatEditTitle,
    )

    return (MessageActionChatEditPhoto, MessageActionChatEditTitle, MessageActionChatDeletePhoto)


def is_notice(message: Any, kinds: tuple[type, ...]) -> bool:
    """Whether this is one of Telegram's own notices of the given kinds.

    The type check comes first and does the real work: anything that is not a
    service message is rejected before its action is even looked at, so a
    message with text can never reach the second half of this expression.
    """
    from telethon.tl.types import MessageService

    return isinstance(message, MessageService) and isinstance(message.action, kinds)


def _client(account: str, directory: Path) -> TelegramClient:
    from telethon import TelegramClient

    api_id, api_hash = api_credentials()
    path = session_path(account, directory=directory)
    if not path.exists():
        raise SystemExit(f"no session for {account!r} at {path}")
    return TelegramClient(str(path.with_suffix("")), api_id, api_hash)


def batched(ids: list[int], size: int = BATCH) -> list[list[int]]:
    return [ids[start : start + size] for start in range(0, len(ids), size)]


async def collect(client: TelegramClient, chat_id: int, kinds: tuple[type, ...], limit: int | None) -> list[int]:
    """Ids of the notices in one chat, newest first."""
    found = []
    async for message in client.iter_messages(chat_id, limit=limit):
        if is_notice(message, kinds):
            found.append(message.id)
    return found


async def run(
    *,
    account: str,
    scope: list[Any],
    directory: Path,
    journal_path: Path | None,
    limit: int | None,
    include_chat_changes: bool,
    apply: bool,
    min_delay: float,
    max_delay: float,
) -> int:
    from telethon.errors import FloodWaitError

    kinds = membership_actions() + (chat_change_actions() if include_chat_changes else ())

    client = _client(account, directory)
    await client.start()  # type: ignore[func-returns-value]
    journal = Journal(journal_path)

    me = await client.get_me()
    print(f"acting as {me.username or me.first_name} (id {me.id})")
    print(f"chats:  {len(scope)}   looking back: {limit or 'all of it'}")
    print("mode:   " + ("APPLY" if apply else "plan only (pass --apply to act)"))
    print()

    removed = failed = 0
    for entry in scope:
        label = f"{entry.chat_id:>15} {entry.title[:36]:<38}"
        if journal.already(entry.chat_id):
            print(f"{label} done earlier")
            continue

        try:
            notices = await collect(client, entry.chat_id, kinds, limit)
        except Exception as err:  # noqa: BLE001 — one unreadable chat must not end the run
            print(f"{label} cannot read: {type(err).__name__}")
            failed += 1
            continue

        if not notices:
            journal.record(entry.chat_id, ok=True, detail="nothing to remove")
            print(f"{label} clean")
            continue
        if not apply:
            print(f"{label} would remove {len(notices)}")
            continue

        try:
            for chunk in batched(notices):
                await client.delete_messages(entry.chat_id, chunk)
                await asyncio.sleep(random.uniform(min_delay, max_delay))  # noqa: S311 — pacing
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

        journal.record(entry.chat_id, ok=True, detail=f"removed {len(notices)}")
        removed += len(notices)
        print(f"{label} removed {len(notices)}")

    await client.disconnect()  # type: ignore[func-returns-value]
    print(f"\nremoved {removed} notices, {failed} chats failed")
    if not apply:
        print("nothing was changed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", default="work")
    parser.add_argument("--chats", type=Path, required=True, help="file of chat ids, one per line")
    parser.add_argument("--sessions-dir", type=Path, default=SESSIONS_DIR)
    parser.add_argument("--journal", type=Path, help="JSONL file recording progress, so a run can resume")
    parser.add_argument("--limit", type=int, default=DEFAULT_LOOKBACK, help="how many recent messages to examine")
    parser.add_argument("--all", action="store_true", help="examine the whole history instead")
    parser.add_argument(
        "--include-chat-changes",
        action="store_true",
        help="also remove 'changed the title / photo' notices",
    )
    parser.add_argument("--min-delay", type=float, default=MIN_DELAY)
    parser.add_argument("--max-delay", type=float, default=MAX_DELAY)
    parser.add_argument("--apply", action="store_true", help="actually delete; without it nothing is removed")
    args = parser.parse_args()

    return asyncio.run(
        run(
            account=args.account,
            scope=read_scope(args.chats),
            directory=args.sessions_dir,
            journal_path=args.journal,
            limit=None if args.all else args.limit,
            include_chat_changes=args.include_chat_changes,
            apply=args.apply,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
