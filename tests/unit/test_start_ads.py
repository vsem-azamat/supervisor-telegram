from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote

import pytest
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message, User
from app.core.config import settings
from app.db import magic_link_store
from app.db.models import AdLead
from app.presentation.telegram.handlers.start import (
    ads_command,
    router,
    start_ad_lead,
    start_ads_info,
    start_web_admin_login,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _start_message(payload: str) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=268388996, type="private"),
        from_user=User(id=268388996, is_bot=False, first_name="Admin"),
        text=f"/start {payload}",
    )


async def _handler_filters_match(handler_name: str, message: Message) -> bool:
    handler = next(item for item in router.message.handlers if getattr(item.callback, "__name__", None) == handler_name)
    assert handler.filters is not None
    data = {"bot": AsyncMock()}
    for filter_object in handler.filters:
        result = await filter_object.call(message, **data)
        if not result:
            return False
        if isinstance(result, dict):
            data.update(result)
    return True


async def test_ads_command_sends_rate_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.webapi, "public_url", "https://konnekt.example")
    message = AsyncMock()
    await ads_command(message)
    message.answer.assert_awaited_once()
    assert "https://konnekt.example/catalog" in message.answer.await_args.args[0]


async def test_start_ads_info_sends_rate_card() -> None:
    message = AsyncMock()
    await start_ads_info(message)
    message.answer.assert_awaited_once()


async def test_start_web_admin_login_router_matches_web_admin_payload() -> None:
    assert await _handler_filters_match("start_web_admin_login", _start_message("web_admin_login"))
    assert not await _handler_filters_match("start_web_admin_login", _start_message("ads"))
    assert not await _handler_filters_match("start_web_admin_login", _start_message("adlead_123"))
    assert not await _handler_filters_match("start_web_admin_login", _start_message("other"))


async def test_start_web_admin_login_issues_magic_link_for_main_admin(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "super_admins", [268388996])
    monkeypatch.setattr(settings.webapi, "auth_mode", "magic_link")
    monkeypatch.setattr(settings.webapi, "public_url", "https://dev.konnekt.azamat.io")
    monkeypatch.setattr(settings.webapi, "magic_link_ttl_minutes", 15)
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=268388996)
    message.chat = SimpleNamespace(type="private")

    await start_web_admin_login(message, session)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "https://dev.konnekt.azamat.io/login#token=" in text
    token = unquote(text.split("/login#token=", 1)[1].split("\n", 1)[0])
    assert await magic_link_store.consume_magic_link(session, token) == 268388996


async def test_start_web_admin_login_rejects_non_main_admin(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "super_admins", [268388996])
    monkeypatch.setattr(settings.webapi, "auth_mode", "magic_link")
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=777)
    message.chat = SimpleNamespace(type="private")

    await start_web_admin_login(message, session)

    message.answer.assert_awaited_once_with("Команда доступна только главному администратору.")


async def test_start_web_admin_login_rejects_non_private_chat(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "super_admins", [268388996])
    monkeypatch.setattr(settings.webapi, "auth_mode", "magic_link")
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=268388996)
    message.chat = SimpleNamespace(type="group")

    await start_web_admin_login(message, session)

    message.answer.assert_awaited_once_with("Команда доступна только в личке с ботом.")


async def test_start_web_admin_login_rejects_when_magic_link_mode_disabled(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "super_admins", [268388996])
    monkeypatch.setattr(settings.webapi, "auth_mode", "telegram")
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=268388996)
    message.chat = SimpleNamespace(type="private")

    await start_web_admin_login(message, session)

    message.answer.assert_awaited_once_with("WEBAPI_AUTH_MODE=magic_link не включен.")


async def test_start_ad_lead_marks_click_and_sends_rate_card(session: AsyncSession) -> None:
    lead = AdLead(chat_id=-1001, user_id=777, snippet="ad")
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    message.answer.assert_awaited_once()
    bot.delete_message.assert_not_awaited()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None


async def test_start_ad_lead_deletes_public_ping(session: AsyncSession) -> None:
    lead = AdLead(
        chat_id=-1001,
        user_id=777,
        snippet="ad",
        reached_via="ping",
        ping_chat_id=-1001,
        ping_message_id=55,
    )
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=55)
    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
    assert lead.ping_chat_id is None
    assert lead.ping_message_id is None


async def test_start_ad_lead_still_answers_when_ping_delete_fails(session: AsyncSession) -> None:
    lead = AdLead(
        chat_id=-1001,
        user_id=777,
        snippet="ad",
        reached_via="ping",
        ping_chat_id=-1001,
        ping_message_id=55,
    )
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    bot.delete_message.side_effect = RuntimeError("message already deleted")
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=55)
    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
    assert lead.ping_chat_id == -1001
    assert lead.ping_message_id == 55
