from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from app.db.models import Chat, Message
from app.sponsored_ads.decisions import apply_ad_decision
from app.sponsored_ads.leads import AdLeadRepository
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from aiogram import Bot

CHAT_A = -1001
CHAT_B = -1002


class _StubBot:
    """Full bot stub for decision orchestration."""

    def __init__(self, *, dm_ok: bool = True) -> None:
        self._dm_ok = dm_ok
        self.deleted: list[tuple[int, int]] = []
        self.banned: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def me(self) -> SimpleNamespace:
        return SimpleNamespace(username="konnekt_moder_bot")

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        self.deleted.append((chat_id, message_id))
        return True

    async def ban_chat_member(self, chat_id: int, user_id: int) -> bool:
        self.banned.append((chat_id, user_id))
        return True

    async def send_message(self, chat_id: int, text: str, disable_web_page_preview: bool = False) -> SimpleNamespace:
        if chat_id > 0 and not self._dm_ok:
            raise RuntimeError("can't initiate conversation")
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=1)


async def test_delete_decision_cleans_creates_lead_and_reaches(session: AsyncSession) -> None:
    session.add_all([Chat(id=CHAT_A, title="A"), Chat(id=CHAT_B, title="B")])
    session.add_all(
        [
            Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"),
            Message(chat_id=CHAT_B, user_id=777, message_id=22, message="spam ad"),
        ]
    )
    await session.commit()
    bot = _StubBot(dm_ok=True)

    status = await apply_ad_decision(
        cast("Bot", bot),
        session,
        action="delete",
        chat_id=CHAT_A,
        message_id=11,
        user_id=777,
    )

    assert set(bot.deleted) == {(CHAT_A, 11), (CHAT_B, 22)}
    assert bot.banned == []
    assert "ЛС" in status
    lead = await AdLeadRepository(session).get_by_id(1)
    assert lead is not None
    assert lead.reached_via == "dm"
    assert lead.snippet == "spam ad"


async def test_delete_decision_falls_back_to_ping(session: AsyncSession) -> None:
    session.add(Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"))
    await session.commit()
    bot = _StubBot(dm_ok=False)

    status = await apply_ad_decision(
        cast("Bot", bot),
        session,
        action="delete",
        chat_id=CHAT_A,
        message_id=11,
        user_id=777,
    )

    assert "пинг" in status
    lead = await AdLeadRepository(session).get_by_id(1)
    assert lead is not None
    assert lead.reached_via == "ping"


async def test_ban_decision_bans_and_skips_outreach(session: AsyncSession) -> None:
    session.add(Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"))
    await session.commit()
    bot = _StubBot()

    status = await apply_ad_decision(
        cast("Bot", bot),
        session,
        action="ban",
        chat_id=CHAT_A,
        message_id=11,
        user_id=777,
    )

    assert bot.banned == [(CHAT_A, 777)]
    assert bot.sent == []  # no outreach on ban
    assert "забанен" in status


async def test_unknown_decision_action_is_rejected_without_side_effects(session: AsyncSession) -> None:
    session.add(Message(chat_id=CHAT_A, user_id=777, message_id=11, message="spam ad"))
    await session.commit()
    bot = _StubBot()

    with pytest.raises(ValueError, match="Unknown ad-review action"):
        await apply_ad_decision(
            cast("Bot", bot),
            session,
            action="archive",
            chat_id=CHAT_A,
            message_id=11,
            user_id=777,
        )

    assert bot.deleted == []
    assert bot.banned == []
    assert bot.sent == []
