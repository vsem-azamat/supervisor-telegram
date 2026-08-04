"""The chat menu button, which points at the catalogue.

Telegram keeps this setting on the bot, not on a message: it is written once at
startup and stays until something writes over it. That is the whole reason the
unconfigured cases here assert a reset rather than a no-op — a deployment that
stops publishing a site would otherwise leave the previous deployment's button
pointing at an address that no longer answers, and nothing would ever clear it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.types import MenuButtonCommands, MenuButtonWebApp
from app.presentation.telegram import bot as bot_module

pytestmark = pytest.mark.unit

SITE = "https://konnekt.example"


async def _set_button(monkeypatch, public_url: str):
    monkeypatch.setattr(bot_module.settings.webapi, "public_url", public_url)
    bot = AsyncMock()

    await bot_module._publish_menu_button(bot)

    return bot.set_chat_menu_button.call_args[1]["menu_button"]


class TestMenuButton:
    async def test_a_configured_site_becomes_a_mini_app(self, monkeypatch) -> None:
        button = await _set_button(monkeypatch, SITE)

        assert isinstance(button, MenuButtonWebApp)
        assert button.web_app.url == SITE

    async def test_a_trailing_slash_does_not_reach_telegram(self, monkeypatch) -> None:
        button = await _set_button(monkeypatch, f"{SITE}/")

        assert isinstance(button, MenuButtonWebApp)
        assert button.web_app.url == SITE

    async def test_no_site_restores_the_command_menu(self, monkeypatch) -> None:
        button = await _set_button(monkeypatch, "")

        assert isinstance(button, MenuButtonCommands)

    async def test_plain_http_restores_the_command_menu(self, monkeypatch) -> None:
        """Telegram requires https for a Mini App; local development has none."""
        button = await _set_button(monkeypatch, "http://localhost:5173")

        assert isinstance(button, MenuButtonCommands)


class TestStartupIsNotHeldHostage:
    async def test_a_failed_menu_button_does_not_stop_the_bot(self, monkeypatch) -> None:
        """Moderation is the job; the menu button is a nicety beside it."""
        monkeypatch.setattr(bot_module.settings.webapi, "public_url", SITE)
        bot = AsyncMock()
        bot.set_chat_menu_button.side_effect = RuntimeError("Telegram said no")

        await bot_module.on_startup(bot)

        bot.delete_webhook.assert_awaited()

    async def test_a_failed_webhook_clear_does_stop_it(self, monkeypatch) -> None:
        """That one means the bot cannot receive updates at all."""
        monkeypatch.setattr(bot_module.settings.webapi, "public_url", SITE)
        bot = AsyncMock()
        bot.delete_webhook.side_effect = RuntimeError("Telegram said no")

        with pytest.raises(RuntimeError):
            await bot_module.on_startup(bot)

        bot.set_chat_menu_button.assert_not_awaited()
