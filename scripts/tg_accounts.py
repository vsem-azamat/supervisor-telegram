"""Sign Telegram accounts in and keep their sessions apart.

Two accounts are involved in running these chats: the personal one that owns
them today, and the working one that is to take over administration. They must
never share a session file — Telethon stores the authorisation key in it, and a
single file for both would mean whichever logged in last silently replaced the
other.

    uv run python scripts/tg_accounts.py login main
    uv run python scripts/tg_accounts.py login work
    uv run python scripts/tg_accounts.py status

`login` is interactive: Telegram sends a code to the account, and a second
prompt appears if it has two-step verification. It has to be run by whoever can
read that code. `status` is not — it only opens the stored sessions and reports
who they belong to, which is how anything automated confirms it is acting as the
account it thinks it is before doing anything.

A session file is the account
-----------------------------
It is not a token scoped to this tool. Anyone holding it can read every chat and
message that account can, send as it, and change its settings; Telegram cannot
tell the difference. They live under `.creds/`, which this repository never
tracks, and they belong nowhere else. Signing out from Telegram's own "active
sessions" list is what actually revokes one — deleting the file only makes it
unusable here.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

# Kept beside the other credentials this machine holds, under a directory the
# repository ignores rather than one it merely has no rule for.
SESSIONS_DIR = Path(".creds/sessions")

# Filenames become session paths, so anything that could climb out of the
# directory or collide with a shell is refused rather than sanitised.
ACCOUNT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")


def session_path(name: str, *, directory: Path = SESSIONS_DIR) -> Path:
    """Where one account's session lives. One file per account, never shared."""
    if not ACCOUNT_NAME.match(name):
        raise SystemExit(f"account name must match {ACCOUNT_NAME.pattern!r}, got {name!r}")
    return directory / f"{name}.session"


def known_accounts(directory: Path = SESSIONS_DIR) -> list[str]:
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.session"))


def api_credentials() -> tuple[int, str]:
    """The api_id/api_hash pair from https://my.telegram.org.

    Both accounts use the same pair: it identifies the application, not the
    account, and the deployment already names these two variables for the
    userbot. Read from the environment so no credential is written to disk here.
    """
    api_id = os.environ.get("TELETHON_API_ID", "").strip()
    api_hash = os.environ.get("TELETHON_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit(
            "set TELETHON_API_ID and TELETHON_API_HASH first — create an application at https://my.telegram.org"
        )
    if not api_id.isdigit():
        raise SystemExit(f"TELETHON_API_ID must be a number, got {api_id!r}")
    return int(api_id), api_hash


def _client(name: str, directory: Path) -> TelegramClient:
    from telethon import TelegramClient

    api_id, api_hash = api_credentials()
    directory.mkdir(parents=True, exist_ok=True)
    # Telethon appends .session itself, so it is handed the path without it.
    return TelegramClient(str(session_path(name, directory=directory).with_suffix("")), api_id, api_hash)


def _describe(me: object) -> str:
    username = getattr(me, "username", None)
    first = getattr(me, "first_name", "") or ""
    last = getattr(me, "last_name", "") or ""
    display = f"@{username}" if username else " ".join(part for part in (first, last) if part) or "?"
    return f"{display} (id {getattr(me, 'id', '?')})"


async def login(name: str, directory: Path) -> int:
    """Sign one account in, or report that it already is."""
    client = _client(name, directory)
    path = session_path(name, directory=directory)
    existed = path.exists()

    await client.connect()
    try:
        if await client.is_user_authorized():
            print(f"{name}: already signed in as {_describe(await client.get_me())}")
            print(f"  session: {path}")
            return 0

        if existed:
            print(f"{name}: session exists but is no longer authorised — signing in again")

        # start() prompts for the phone number, the code Telegram sends, and the
        # two-step password when one is set.
        await client.start()  # type: ignore[func-returns-value]
        print(f"{name}: signed in as {_describe(await client.get_me())}")
        print(f"  session: {path}")
        print("  this file is the account — keep it off shared machines and out of backups")
        return 0
    finally:
        await client.disconnect()  # type: ignore[func-returns-value]


async def status(names: list[str], directory: Path) -> int:
    """Report who each stored session belongs to, without prompting for anything.

    Deliberately non-interactive: this is the check an unattended run makes
    before it acts, and a hidden prompt there would hang rather than fail.
    """
    if not names:
        print(f"no sessions in {directory}/ — run `login <account>` first")
        return 1

    failures = 0
    for name in names:
        path = session_path(name, directory=directory)
        if not path.exists():
            print(f"{name:<10} missing        {path}")
            failures += 1
            continue

        client = _client(name, directory)
        try:
            await client.connect()
            if await client.is_user_authorized():
                print(f"{name:<10} authorised    {_describe(await client.get_me())}")
            else:
                print(f"{name:<10} NOT AUTHORISED — sign in again, or it was revoked from Telegram")
                failures += 1
        except Exception as err:  # noqa: BLE001 — one broken session must not hide the others
            print(f"{name:<10} error         {type(err).__name__}: {err}")
            failures += 1
        finally:
            await client.disconnect()  # type: ignore[func-returns-value]

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=SESSIONS_DIR,
        help=f"where session files live (default: {SESSIONS_DIR})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    signin = sub.add_parser("login", help="sign an account in and store its session")
    signin.add_argument("account", help="short name for this account, e.g. main or work")

    check = sub.add_parser("status", help="report who each stored session belongs to")
    check.add_argument("account", nargs="*", help="accounts to check; default is every stored session")

    args = parser.parse_args()

    if args.command == "login":
        return asyncio.run(login(args.account, args.sessions_dir))

    names = args.account or known_accounts(args.sessions_dir)
    return asyncio.run(status(names, args.sessions_dir))


if __name__ == "__main__":
    sys.exit(main())
