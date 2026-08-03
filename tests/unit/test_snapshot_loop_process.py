"""Which process records member counts.

This is asserted as text, for the same reason the public/admin split is: the
rule spans two processes and nothing inside either of them can see the other.
The snapshot loop was started from the web API's lifespan for as long as it
existed, and every part of that looked correct — the call was there, the
argument was there, the guard was there. What was missing sat in a different
file: the container it asks for a Telethon client is a per-process singleton
wired by the bot's startup, and `moderator_userbot.session` is mounted into the
bot container alone.

So it logged "telethon unavailable" once per restart and wrote nothing, for its
whole life. No test failed, because the loop's own tests call `snapshot_once`
directly and pass it a client.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APP = Path(__file__).resolve().parents[2] / "app"
BOT = APP / "presentation" / "telegram" / "bot.py"
WEBAPI = APP / "webapi" / "main.py"
COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yaml"


def test_the_bot_process_starts_it() -> None:
    assert "run_snapshot_loop" in BOT.read_text(encoding="utf-8")


def test_the_web_api_does_not() -> None:
    """It cannot. Starting it there is a no-op that looks like a feature."""
    assert "run_snapshot_loop" not in WEBAPI.read_text(encoding="utf-8")


def test_the_session_is_mounted_where_the_loop_runs() -> None:
    """The reason for both of the above, in the file that decides it.

    If the session ever moves, this fails and the loop has to move with it —
    which is the conversation that should happen, rather than a container
    quietly reading an account it does not have.
    """
    compose = COMPOSE.read_text(encoding="utf-8")
    bot_block = compose.split("  bot:", 1)[1].split("\n  webapi:", 1)[0]
    assert "moderator_userbot.session" in bot_block
