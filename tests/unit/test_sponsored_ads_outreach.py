from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from app.sponsored_ads.outreach import reach_advertiser

if TYPE_CHECKING:
    from aiogram import Bot

USER_ID = 777
ORIGIN_CHAT = -1001


class _StubBot:
    """Bot stub: positive chat_id == DM to user, negative == group ping."""

    def __init__(self, *, dm_ok: bool = True, ping_ok: bool = True) -> None:
        self._dm_ok = dm_ok
        self._ping_ok = ping_ok
        self.sent: list[tuple[int, str]] = []

    async def me(self) -> SimpleNamespace:
        return SimpleNamespace(username="konnekt_moder_bot")

    async def send_message(self, chat_id: int, text: str, disable_web_page_preview: bool = False) -> SimpleNamespace:
        if chat_id > 0 and not self._dm_ok:
            raise RuntimeError("bot can't initiate conversation with a user")
        if chat_id < 0 and not self._ping_ok:
            raise RuntimeError("chat send failed")
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=1)


async def test_reach_advertiser_dm_success() -> None:
    bot = _StubBot(dm_ok=True)
    result = await reach_advertiser(cast("Bot", bot), user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result.reached_via == "dm"
    assert result.ping_chat_id is None
    assert result.ping_message_id is None
    assert bot.sent[0][0] == USER_ID
    assert "adlead_5" in bot.sent[0][1]


async def test_reach_advertiser_falls_back_to_ping() -> None:
    bot = _StubBot(dm_ok=False, ping_ok=True)
    result = await reach_advertiser(cast("Bot", bot), user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result.reached_via == "ping"
    assert result.ping_chat_id == ORIGIN_CHAT
    assert result.ping_message_id == 1
    assert bot.sent[0][0] == ORIGIN_CHAT
    assert "adlead_5" in bot.sent[0][1]


async def test_reach_advertiser_failed_when_both_fail() -> None:
    bot = _StubBot(dm_ok=False, ping_ok=False)
    result = await reach_advertiser(cast("Bot", bot), user_id=USER_ID, origin_chat_id=ORIGIN_CHAT, lead_id=5)
    assert result.reached_via == "failed"
    assert result.ping_chat_id is None
    assert result.ping_message_id is None
    assert bot.sent == []
