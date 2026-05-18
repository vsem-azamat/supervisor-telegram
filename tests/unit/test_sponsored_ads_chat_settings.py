from __future__ import annotations

import pytest
from app.db.models import Chat
from app.db.repositories.chat import ChatRepository

pytestmark = pytest.mark.asyncio


async def test_chat_sponsored_ads_disabled_by_default(session) -> None:
    chat = Chat(id=-100100, title="Admissions chat")
    session.add(chat)
    await session.commit()

    repo = ChatRepository(session)
    saved = await repo.get_by_id(chat.id)

    assert saved is not None
    assert saved.ad_enabled is False


async def test_chat_repository_can_toggle_sponsored_ads(session) -> None:
    repo = ChatRepository(session)
    await repo.merge_chat(-100100, title="Admissions chat")

    enabled = await repo.set_ad_enabled(-100100, enabled=True)
    assert enabled is not None
    assert enabled.ad_enabled is True

    disabled = await repo.set_ad_enabled(-100100, enabled=False)
    assert disabled is not None
    assert disabled.ad_enabled is False


async def test_chat_repository_save_preserves_sponsored_ads_flag(session) -> None:
    repo = ChatRepository(session)
    chat = Chat(id=-100100, title="Admissions chat", ad_enabled=True)

    await repo.save(chat)
    chat.title = "Updated admissions chat"
    await repo.save(chat)

    saved = await repo.get_by_id(chat.id)
    assert saved is not None
    assert saved.title == "Updated admissions chat"
    assert saved.ad_enabled is True
