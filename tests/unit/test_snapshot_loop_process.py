"""Which process records member counts.

Asserted as text, for the same reason the public/admin split is: the rule spans
two processes and nothing inside either of them can see the other.

The loop lived in the web API's lifespan and had never written a row. Every
part of that call looked correct — the guard, the argument, the log line. What
was missing sat in a different file: it read through a Telethon client held by
a per-process singleton the bot wires at startup, and the account's session is
on a developer's machine rather than on the server.

It reads through the bot token now, so that particular trap is gone. The rule
that remains is narrower and still worth pinning: one home for the loop, and it
is the process that owns a long-lived bot. Two processes running it would
double every row, and the web API is the one that gets restarted under load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APP = Path(__file__).resolve().parents[2] / "app"
BOT = APP / "presentation" / "telegram" / "bot.py"
WEBAPI = APP / "webapi" / "main.py"


def test_the_bot_process_starts_it() -> None:
    assert "run_snapshot_loop" in BOT.read_text(encoding="utf-8")


def test_the_web_api_does_not() -> None:
    assert "run_snapshot_loop" not in WEBAPI.read_text(encoding="utf-8")


def test_it_does_not_reach_for_the_client_api() -> None:
    """The counts are a bot method. Reaching past that is what broke them.

    Matched on the import rather than the word, because the module's own
    docstring explains the history and should keep being allowed to.
    """
    assert "app.telethon" not in (APP / "chats" / "snapshots.py").read_text(encoding="utf-8")
