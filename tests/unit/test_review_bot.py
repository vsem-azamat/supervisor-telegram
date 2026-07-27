"""The web API must send review drafts under the identity that owns their buttons.

Telegram routes an inline-keyboard callback to the sending bot, and
``channel_review_router`` lives on the moderator dispatcher. Sending a review
message under any other identity produces buttons that silently do nothing.

There used to be two identities to choose between; the assistant is gone and
the choice with it. The test stays because the constraint did not.
"""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.webapi.services.review_bot import build_review_bot

pytestmark = pytest.mark.asyncio


async def test_review_drafts_go_out_as_the_moderator() -> None:
    bot = build_review_bot()
    try:
        assert bot.token == settings.telegram.token
    finally:
        await bot.session.close()
