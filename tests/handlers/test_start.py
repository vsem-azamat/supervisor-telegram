"""The front door: `/start`, `/help`, and the way into the console.

`/start` and `/help` used to be one handler, so the first thing anybody saw was
a справочник — twenty lines of commands, most of which they could not run,
which then deleted itself after a minute. The site was mentioned nowhere, and
the console could only be reached by knowing that a command called `/adminlink`
existed.

What is pinned here is who sees what. The wording will move; the rule that a
stranger is not handed the moderator's toolbox, and that the console button
belongs to super administrators alone, should not.
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.presentation.telegram.handlers import start as start_handlers

from tests.telegram_helpers import TelegramObjectFactory, create_admin_user, create_normal_user

SUPER_ADMIN_ID = 123456789
SITE = "https://konnekt.example"


@pytest.fixture
def telegram_factory():
    return TelegramObjectFactory()


@pytest.fixture
def admin_repo():
    repo = AsyncMock()
    repo.is_admin.return_value = False
    repo.chats_for.return_value = []
    return repo


@pytest.fixture
def site(monkeypatch):
    """A configured public URL, so the web buttons have somewhere to point."""
    monkeypatch.setattr(start_handlers.settings.webapi, "public_url", SITE)
    monkeypatch.setattr(start_handlers.settings.webapi, "auth_mode", "magic_link")
    monkeypatch.setattr(start_handlers.settings.admin, "super_admins", [SUPER_ADMIN_ID])


def _private(factory, command: str, user):
    return factory.create_command_message(
        command=command, user=user, chat=factory.create_chat(id=user.id, type="private", title=None)
    )


def _in_group(factory, command: str, user):
    return factory.create_command_message(command=command, user=user, chat=factory.create_chat())


def _answered(message) -> tuple[str, list]:
    text = message.answer.call_args[0][0]
    markup = message.answer.call_args[1].get("reply_markup")
    buttons = [b for row in markup.inline_keyboard for b in row] if markup else []
    return text, buttons


@pytest.mark.handlers
class TestStart:
    async def test_a_stranger_gets_buttons_not_a_command_list(self, telegram_factory, admin_repo, site):
        """The greeting answers "what is this", not "what can you type"."""
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        text, buttons = _answered(message)
        assert "/mute" not in text
        assert "/banall" not in text
        assert "/help" in text
        assert len(buttons) >= 2

    async def test_the_first_button_goes_to_the_catalogue(self, telegram_factory, admin_repo, site):
        """The question people arrive with is "where is my faculty's chat".

        As a Mini App rather than a link: opened as a site, a tap on a chat
        leaves Telegram for a browser which then reopens Telegram.
        """
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert buttons[0].web_app is not None
        assert buttons[0].web_app.url == SITE
        assert buttons[0].url is None

    async def test_an_advertiser_has_somewhere_to_go(self, telegram_factory, admin_repo, site):
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert any(b.web_app and b.web_app.url == f"{SITE}/ads" for b in buttons)

    async def test_in_a_group_the_site_stays_an_ordinary_link(self, telegram_factory, admin_repo, site):
        """Telegram refuses a web_app button outside a private chat.

        It refuses the message, not the button: `/start` in a group would answer
        nothing at all rather than answer with one button missing.
        """
        message = _in_group(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert all(b.web_app is None for b in buttons)
        assert buttons[0].url == SITE

    async def test_a_site_without_tls_stays_an_ordinary_link(self, telegram_factory, admin_repo, monkeypatch):
        """Telegram requires https for a Mini App; local development has none."""
        monkeypatch.setattr(start_handlers.settings.webapi, "public_url", "http://localhost:5173")
        monkeypatch.setattr(start_handlers.settings.admin, "super_admins", [])
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert all(b.web_app is None for b in buttons)
        assert buttons[0].url == "http://localhost:5173"

    async def test_the_greeting_is_not_deleted(self, telegram_factory, admin_repo, site):
        """It is the first screen of the product, not a service reply.

        The old one self-destructed after sixty seconds, taking the only thing
        that explained the bot with it.
        """
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        with patch.object(start_handlers.other, "sleep_and_delete") as scheduled:
            await start_handlers.start_private(message, admin_repo)

        scheduled.assert_not_called()

    async def test_no_console_button_for_an_ordinary_person(self, telegram_factory, admin_repo, site):
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert not any("онсол" in b.text for b in buttons)

    async def test_a_super_admin_is_offered_the_console(self, telegram_factory, admin_repo, site):
        """This replaces having to know that `/adminlink` exists."""
        message = _private(telegram_factory, "start", create_admin_user(id=SUPER_ADMIN_ID))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        console = [b for b in buttons if "онсол" in b.text]
        assert len(console) == 1
        # A callback, not a URL: minting the link when the menu is drawn burns
        # its lifetime while the person is still reading.
        assert console[0].url is None
        assert console[0].callback_data

    async def test_without_a_configured_site_it_still_answers(self, telegram_factory, admin_repo, monkeypatch):
        """A missing WEBAPI_PUBLIC_URL must not produce a button to nowhere."""
        monkeypatch.setattr(start_handlers.settings.webapi, "public_url", "")
        monkeypatch.setattr(start_handlers.settings.admin, "super_admins", [])
        message = _private(telegram_factory, "start", create_normal_user(id=555))

        await start_handlers.start_private(message, admin_repo)

        _, buttons = _answered(message)
        assert all(b.url != "" for b in buttons)
        assert not any(b.url and b.url.endswith("/ads") for b in buttons)


@pytest.mark.handlers
class TestHelp:
    async def test_a_stranger_sees_only_what_they_can_run(self, telegram_factory, admin_repo, site):
        message = _private(telegram_factory, "help", create_normal_user(id=555))

        await start_handlers.help_command(message, admin_repo)

        text, _ = _answered(message)
        assert "/report" in text
        assert "/mute" not in text
        assert "/banall" not in text

    async def test_a_moderator_sees_the_chat_scoped_commands(self, telegram_factory, admin_repo, site):
        admin_repo.is_admin.return_value = True
        admin_repo.chats_for.return_value = [-100_1, -100_2]
        message = _private(telegram_factory, "help", create_normal_user(id=555))

        await start_handlers.help_command(message, admin_repo)

        text, _ = _answered(message)
        assert "/mute" in text
        assert "/ban" in text
        # Reaching every chat at once is not theirs to do.
        assert "/banall" not in text

    async def test_a_super_admin_sees_the_global_ones(self, telegram_factory, admin_repo, site):
        message = _private(telegram_factory, "help", create_admin_user(id=SUPER_ADMIN_ID))

        await start_handlers.help_command(message, admin_repo)

        text, _ = _answered(message)
        assert "/banall" in text
        assert "/blacklist" in text

    async def test_the_dead_and_the_debug_commands_are_not_advertised(self, telegram_factory, admin_repo, site):
        """`/adminlink` no longer exists, and `/json` is a debugging dump."""
        message = _private(telegram_factory, "help", create_admin_user(id=SUPER_ADMIN_ID))

        await start_handlers.help_command(message, admin_repo)

        text, _ = _answered(message)
        assert "/adminlink" not in text
        assert "/webadmin" not in text
        assert "/json" not in text


@pytest.mark.handlers
class TestTheConsoleButton:
    async def test_a_stranger_pressing_it_gets_nothing(self, telegram_factory, site):
        """The keyboard is only drawn for super admins, but the callback data is
        guessable and arrives outside the layout that decided to draw it."""
        message = telegram_factory.create_message()
        callback = telegram_factory.create_callback_query(user=create_normal_user(id=555), message=message)

        await start_handlers.open_console(callback)

        message.answer.assert_not_called()
        assert "дминистратор" in callback.answer.call_args[0][0]

    async def test_a_super_admin_gets_a_one_time_link(self, telegram_factory, site):
        message = telegram_factory.create_message()
        callback = telegram_factory.create_callback_query(user=create_admin_user(id=SUPER_ADMIN_ID), message=message)

        with patch.object(start_handlers, "_mint_magic_link", AsyncMock(return_value="tok3n")):
            await start_handlers.open_console(callback)

        answered = message.answer.call_args[0][0]
        assert f"{SITE}/login#token=tok3n" in answered

    async def test_it_says_so_when_magic_links_are_off(self, telegram_factory, monkeypatch):
        monkeypatch.setattr(start_handlers.settings.webapi, "auth_mode", "telegram")
        monkeypatch.setattr(start_handlers.settings.admin, "super_admins", [SUPER_ADMIN_ID])
        message = telegram_factory.create_message()
        callback = telegram_factory.create_callback_query(user=create_admin_user(id=SUPER_ADMIN_ID), message=message)

        await start_handlers.open_console(callback)

        assert message.answer.call_args[0][0]
        assert "magic_link" in message.answer.call_args[0][0]
