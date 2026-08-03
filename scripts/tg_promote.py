"""Make one account an administrator across a list of chats.

The handover step: the account that owns these chats appoints a second one, so
day-to-day management moves off the personal account. Nothing is taken away from
anybody — see below — and ownership is never transferred.

    uv run python scripts/tg_promote.py --account main --target @work_azamat --chats scope.txt
    uv run python scripts/tg_promote.py --account main --target @work_azamat --chats scope.txt --apply

Without ``--apply`` every chat is inspected and the intended action printed, and
not a single write is sent.

It never takes anything away
---------------------------
There is no demotion, no removal, no leaving, and no transfer of ownership here.
The last one is deliberate and worth stating twice: ``channels.editCreator`` is
the call that hands a chat to somebody else, it is irreversible without the new
owner's cooperation, and this file does not contain it. The personal account
keeps everything it has until a human removes it by hand, having seen the second
account work.

Pacing
------
Telegram treats a burst of membership changes from one account as spam, and the
limit lands on the account doing the appointing — the one that owns the chats.
So the delay between writes is randomised rather than fixed, a ``FloodWaitError``
is obeyed rather than retried through, and a ``PeerFloodError`` stops the run
outright: at that point the account is already flagged and continuing makes it
worse. The journal makes stopping cheap — a later run picks up where this one
left off.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tg_accounts import SESSIONS_DIR, api_credentials, session_path  # noqa: E402

if TYPE_CHECKING:
    from telethon import TelegramClient

# Randomised so the sequence does not look mechanical. The lower bound matters
# more than the upper one: it is what keeps a run under Telegram's radar.
MIN_DELAY = 4.0
MAX_DELAY = 12.0

# Telegram truncates an admin title beyond this.
MAX_TITLE = 16


def admin_rights() -> dict[str, bool]:
    """Every administrator right, and nothing that transfers the chat.

    ``add_admins`` is included on purpose: the point of this account is to
    replace the personal one, and an admin who cannot appoint admins cannot
    invite the moderator bot back or hand over in turn.

    ``anonymous`` is not a right so much as a display choice, and moderation
    that hides who performed it is worse than moderation that does not.
    """
    return {
        "change_info": True,
        "post_messages": True,
        "edit_messages": True,
        "delete_messages": True,
        "ban_users": True,
        "invite_users": True,
        "pin_messages": True,
        "add_admins": True,
        "manage_call": True,
        "anonymous": False,
    }


@dataclass
class Target:
    chat_id: int
    title: str = ""


def read_scope(path: Path) -> list[Target]:
    """Chat ids to work through, one per line.

    Anything after the id on a line is treated as a human-readable label, so a
    list can be pasted straight out of a report without editing.
    """
    targets = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        targets.append(Target(int(parts[0]), parts[1].strip() if len(parts) > 1 else ""))
    return targets


class Journal:
    """Which chats are already done, so an interrupted run resumes."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.done: set[int] = set()
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("ok"):
                    self.done.add(int(entry["chat_id"]))

    def already(self, chat_id: int) -> bool:
        return chat_id in self.done

    def record(self, chat_id: int, *, ok: bool, detail: str = "") -> None:
        if ok:
            self.done.add(chat_id)
        if not self.path:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"chat_id": chat_id, "ok": ok, "detail": detail}, ensure_ascii=False) + "\n")


def _client(account: str, directory: Path) -> TelegramClient:
    from telethon import TelegramClient

    api_id, api_hash = api_credentials()
    path = session_path(account, directory=directory)
    if not path.exists():
        raise SystemExit(f"no session for {account!r} at {path}")
    return TelegramClient(str(path.with_suffix("")), api_id, api_hash)


async def already_admin(client: TelegramClient, chat_id: int, user: Any) -> bool:
    from telethon.errors import UserNotParticipantError

    try:
        permissions = await client.get_permissions(chat_id, user)
    except UserNotParticipantError:
        return False
    except Exception:  # noqa: BLE001 — treated as "not yet", the promotion will say why
        return False
    return bool(permissions.is_admin)


async def promote(client: TelegramClient, chat_id: int, user: Any, title: str) -> None:
    """Appoint the account. Adds it to the chat first if Telegram insists.

    Supergroups accept an administrator who is not yet a member and add them in
    the same step; the older group type does not, and asks for the invitation to
    happen first.
    """
    from telethon.errors import UserNotParticipantError
    from telethon.tl import functions

    try:
        await client.edit_admin(chat_id, user, title=title[:MAX_TITLE], **admin_rights())
    except UserNotParticipantError:
        await client(functions.channels.InviteToChannelRequest(channel=chat_id, users=[user]))
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))  # noqa: S311 — pacing, not cryptography
        await client.edit_admin(chat_id, user, title=title[:MAX_TITLE], **admin_rights())


async def run(
    *,
    account: str,
    target: str,
    scope: list[Target],
    title: str,
    directory: Path,
    journal_path: Path | None,
    apply: bool,
    min_delay: float,
    max_delay: float,
) -> int:
    from telethon.errors import FloodWaitError, PeerFloodError

    client = _client(account, directory)
    await client.start()  # type: ignore[func-returns-value]
    journal = Journal(journal_path)

    me = await client.get_me()
    user = await client.get_entity(target)
    print(f"acting as {me.username or me.first_name} (id {me.id})")
    print(f"appointing {getattr(user, 'username', None) or user.id} in {len(scope)} chats")
    print("mode:      " + ("APPLY" if apply else "plan only (pass --apply to act)"))
    print()

    promoted = skipped = failed = 0
    try:
        for entry in scope:
            label = f"{entry.chat_id:>12} {entry.title[:38]:<40}"
            if journal.already(entry.chat_id):
                print(f"{label} done earlier")
                skipped += 1
                continue
            if await already_admin(client, entry.chat_id, user):
                journal.record(entry.chat_id, ok=True, detail="already admin")
                print(f"{label} already admin")
                skipped += 1
                continue
            if not apply:
                print(f"{label} would promote")
                continue

            try:
                await promote(client, entry.chat_id, user, title)
            except PeerFloodError:
                # Already flagged. Continuing is how a temporary limit becomes a
                # long one, so the run ends here and the journal keeps the place.
                journal.record(entry.chat_id, ok=False, detail="peer_flood")
                print(f"{label} PEER_FLOOD — stopping. Resume in a few hours with the same journal.")
                failed += 1
                break
            except FloodWaitError as err:
                journal.record(entry.chat_id, ok=False, detail=f"flood_wait {err.seconds}s")
                print(f"{label} flood wait {err.seconds}s — stopping. Resume after that.")
                failed += 1
                break
            except Exception as err:  # noqa: BLE001 — one chat failing must not end the rest
                journal.record(entry.chat_id, ok=False, detail=f"{type(err).__name__}: {err}")
                print(f"{label} failed: {type(err).__name__}")
                failed += 1
                continue

            journal.record(entry.chat_id, ok=True)
            promoted += 1
            print(f"{label} promoted")
            await asyncio.sleep(random.uniform(min_delay, max_delay))  # noqa: S311 — pacing, not cryptography
    finally:
        await client.disconnect()  # type: ignore[func-returns-value]

    print(f"\npromoted {promoted}, skipped {skipped}, failed {failed}")
    if not apply:
        print("nothing was changed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", default="main", help="session doing the appointing")
    parser.add_argument("--target", required=True, help="account to promote, e.g. @work_azamat")
    parser.add_argument("--chats", type=Path, required=True, help="file of chat ids, one per line")
    parser.add_argument("--title", default="", help=f"admin title shown in the chat, up to {MAX_TITLE} characters")
    parser.add_argument("--sessions-dir", type=Path, default=SESSIONS_DIR)
    parser.add_argument("--journal", type=Path, help="JSONL file recording progress, so a run can resume")
    parser.add_argument("--min-delay", type=float, default=MIN_DELAY, help="shortest pause between writes")
    parser.add_argument("--max-delay", type=float, default=MAX_DELAY, help="longest pause between writes")
    parser.add_argument("--apply", action="store_true", help="actually appoint; without it nothing is sent")
    args = parser.parse_args()

    return asyncio.run(
        run(
            account=args.account,
            target=args.target,
            scope=read_scope(args.chats),
            title=args.title,
            directory=args.sessions_dir,
            journal_path=args.journal,
            apply=args.apply,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
