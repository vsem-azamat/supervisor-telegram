"""The bot's own handle, asked for once and remembered.

Reachable without an app, which is the point of moving it off `app.state`: the
cooldown after a failing Telegram used to be three `getattr` defaults in a
route, and the only way to exercise it was two HTTP requests and a stub bot.
"""

import pytest

from students_cz.services.telegram import BotHandle

from .conftest import BrokenBot, StubBot

pytestmark = pytest.mark.asyncio


async def test_telegram_is_asked_once_and_the_answer_kept() -> None:
    bot = StubBot("student_cz_bot")
    handle = BotHandle(bot)

    assert await handle.username() == "student_cz_bot"
    assert await handle.username() == "student_cz_bot"
    assert bot.calls == 1


async def test_no_bot_is_no_handle_rather_than_an_error() -> None:
    """How the API runs locally, and under test."""
    assert await BotHandle(None).username() is None


async def test_a_failing_telegram_is_not_asked_again_immediately() -> None:
    now = [1000.0]
    bot = BrokenBot()
    handle = BotHandle(bot, cooldown=30.0, clock=lambda: now[0])

    assert await handle.username() is None
    assert await handle.username() is None
    assert bot.calls == 1, "every landing visit would otherwise call Telegram"


async def test_and_is_asked_again_once_the_cooldown_passes() -> None:
    now = [1000.0]
    bot = BrokenBot()
    handle = BotHandle(bot, cooldown=30.0, clock=lambda: now[0])

    await handle.username()
    now[0] += 31.0
    assert await handle.username() is None
    assert bot.calls == 2, "a bot that came back must be reachable again"


async def test_a_bot_with_no_public_handle_is_not_asked_again_either() -> None:
    """Nothing is cached in that case, so the cooldown is what stops the loop."""

    now = [1000.0]
    bot = StubBot(username=None)
    handle = BotHandle(bot, cooldown=30.0, clock=lambda: now[0])

    assert await handle.username() is None
    assert await handle.username() is None
    assert bot.calls == 1
