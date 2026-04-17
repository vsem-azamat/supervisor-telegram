"""Tests for buttons service."""

import pytest
from app.presentation.telegram.utils import buttons


@pytest.mark.unit
class TestButtonsService:
    async def test_get_contacts_buttons(self):
        """Static button layout for the /start contacts menu."""
        builder = await buttons.get_contacts_buttons()

        keyboard = builder.as_markup()
        assert len(keyboard.inline_keyboard) == 2  # adjust(1) → two rows

        dev_button = keyboard.inline_keyboard[0][0]
        assert dev_button.text == "Dev"
        assert dev_button.url == "https://t.me/vsem_azamat"

        github_button = keyboard.inline_keyboard[1][0]
        assert github_button.text == "GitHub"
        assert github_button.url == "https://github.com/vsem-azamat/moderator-bot"
