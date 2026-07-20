"""The web API must send review drafts under the identity that owns their buttons.

Telegram routes an inline-keyboard callback to the sending bot, and
``channel_review_router`` lives on the assistant dispatcher whenever the
assistant is active. Picking the wrong identity here produces review messages
whose approve/reject buttons silently do nothing.
"""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.webapi.services.review_bot import build_review_bot

pytestmark = pytest.mark.asyncio

ASSISTANT_TOKEN = "222222:ASSISTANT-TOKEN"  # noqa: S105 — test fixture, not a credential


@pytest.fixture
def assistant_settings():
    original = (settings.assistant.enabled, settings.assistant.token)
    yield
    settings.assistant.enabled, settings.assistant.token = original


async def test_uses_assistant_identity_when_assistant_is_active(assistant_settings) -> None:
    settings.assistant.enabled, settings.assistant.token = True, ASSISTANT_TOKEN

    bot = build_review_bot()
    try:
        assert bot.token == ASSISTANT_TOKEN
    finally:
        await bot.session.close()


@pytest.mark.parametrize(
    ("enabled", "token", "case"),
    [
        (False, ASSISTANT_TOKEN, "assistant disabled"),
        (True, "", "assistant enabled but tokenless"),
    ],
)
async def test_falls_back_to_moderator_identity(assistant_settings, enabled, token, case) -> None:
    settings.assistant.enabled, settings.assistant.token = enabled, token

    bot = build_review_bot()
    try:
        assert bot.token == settings.telegram.token, case
    finally:
        await bot.session.close()
