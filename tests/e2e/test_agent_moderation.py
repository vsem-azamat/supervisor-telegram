"""End-to-end tests for moderation: /report, /spam (mechanical), escalation callbacks.

Uses:
- FakeTelegramServer to simulate Telegram Bot API
- SQLite in-memory for DB (fast, no docker needed)
- /report and /spam are now mechanical (no LLM) — they forward to admin chat
- Escalation callbacks use AgentCore.execute_action directly (no injected agent_core)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    MessageEntity,
    Update,
    User,
)
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from app.infrastructure.db.models import AgentEscalation
from app.presentation.telegram.middlewares import (
    DependenciesMiddleware,
    HistoryMiddleware,
    ManagedChatsMiddleware,
)
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.fake_telegram import FakeTelegramServer


def _build_router() -> Any:
    """Build a fresh router tree for testing (avoids 'already attached' errors)."""
    from aiogram import Router
    from app.presentation.telegram.handlers import (
        admin,
        agent_handler,
        events,
        groups,
        moderation,
        service,
        start,
    )
    from app.presentation.telegram.middlewares import chat_type as chat_type_mw

    # Re-create sub-routers to avoid reuse issues
    r = Router()

    # The agent_router is a module-level singleton — we can include it once per test
    # by using a fresh parent router each time.
    # But sub-routers (agent_router, moderation_router etc.) are singletons too.
    # We must detach them from any previous parent first.
    sub_routers = [
        agent_handler.agent_router,
        moderation.moderation_router,
        start.router,
        admin.admin_router,
        groups.groups_router,
        service.router,
        events.router,
    ]
    for sr in sub_routers:
        sr._parent_router = None  # type: ignore[assignment]  # force detach

    # Re-wire middlewares on sub-routers (same as handlers/__init__.py)
    agent_handler.agent_router.message.middleware(chat_type_mw.ChatTypeMiddleware(["group", "supergroup"]))

    r.include_router(agent_handler.agent_router)
    r.include_router(moderation.moderation_router)
    r.include_router(start.router)
    r.include_router(admin.admin_router)
    r.include_router(groups.groups_router)
    r.include_router(service.router)
    r.include_router(events.router)
    return r


# ---- Test users / chats ----

SUPER_ADMIN_ID = 123456789  # matches conftest env ADMIN_SUPER_ADMINS
REPORTER_ID = 111111111
TARGET_USER_ID = 222222222
CHAT_ID = -1001234567890


def _make_user(uid: int, first_name: str = "User", username: str | None = None) -> dict[str, Any]:
    return {
        "id": uid,
        "is_bot": False,
        "first_name": first_name,
        "username": username,
    }


def _make_chat(cid: int = CHAT_ID) -> dict[str, Any]:
    return {
        "id": cid,
        "type": "supergroup",
        "title": "Test Chat",
    }


def _make_message(
    text: str,
    from_user_id: int = REPORTER_ID,
    message_id: int = 42,
    chat_id: int = CHAT_ID,
    entities: list[dict[str, Any]] | None = None,
    reply_to_message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "from": _make_user(from_user_id, username=f"user_{from_user_id}"),
        "chat": _make_chat(chat_id),
        "date": int(datetime.now(UTC).timestamp()),
        "text": text,
        "entities": entities or [],
        "reply_to_message": reply_to_message,
    }


def _make_command_message(
    command: str,
    from_user_id: int = REPORTER_ID,
    reply_to_message: dict[str, Any] | None = None,
    message_id: int = 50,
) -> dict[str, Any]:
    text = f"/{command}"
    entities = [{"type": "bot_command", "offset": 0, "length": len(text)}]
    return _make_message(
        text=text,
        from_user_id=from_user_id,
        message_id=message_id,
        entities=entities,
        reply_to_message=reply_to_message,
    )


def _make_target_message(text: str = "Buy cheap diploma!!! Contact @scammer") -> dict[str, Any]:
    """The message being reported."""
    return _make_message(
        text=text,
        from_user_id=TARGET_USER_ID,
        message_id=30,
    )


def _make_callback_query(
    data: str,
    from_user_id: int = SUPER_ADMIN_ID,
    message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": "cb_123",
        "from": _make_user(from_user_id, first_name="Admin", username="super_admin"),
        "chat_instance": "12345",
        "data": data,
        "message": message or _make_message("Escalation text", from_user_id=5145935834, message_id=999),
    }


# ---- Fixtures ----


@pytest_asyncio.fixture()
async def db_session(db_session_maker):
    async with db_session_maker() as session:
        yield session


@pytest_asyncio.fixture()
async def fake_tg(fake_tg: FakeTelegramServer):
    """Wrap shared fake_tg with chat admin setup for moderation tests."""
    fake_tg.set_chat_admins(CHAT_ID, [SUPER_ADMIN_ID])
    yield fake_tg


@pytest_asyncio.fixture()
async def bot(fake_tg: FakeTelegramServer):
    """Bot connected to fake Telegram server."""
    from aiogram.client.telegram import TelegramAPIServer

    api_server = TelegramAPIServer(
        base=f"{fake_tg.base_url}/bot{{token}}/{{method}}",
        file=f"{fake_tg.base_url}/file/bot{{token}}/{{path}}",
        is_local=True,
    )
    session = AiohttpSession(api=api_server)
    b = Bot(
        token="123456:ABC-DEF1234567890",
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    yield b
    await b.session.close()


@pytest_asyncio.fixture()
async def dispatcher(
    bot: Bot,
    db_session_maker: async_sessionmaker[AsyncSession],
    fake_tg: FakeTelegramServer,
):
    """Fully wired dispatcher with middlewares and handlers."""
    dp = Dispatcher()

    dp.update.middleware(DependenciesMiddleware(session_pool=db_session_maker, bot=bot))
    dp.update.middleware(ManagedChatsMiddleware())
    dp.update.middleware(HistoryMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.include_router(_build_router())

    yield dp


# ---- Tests ----


@pytest.mark.e2e
class TestReportCommand:
    """Tests for /report and /spam commands (mechanical forwarding)."""

    async def test_report_without_reply_shows_hint(self, dispatcher: Dispatcher, bot: Bot, fake_tg: FakeTelegramServer):
        """Sending /report without replying to a message should show a hint."""
        update = Update(
            update_id=1,
            message=Message(
                message_id=50,
                date=datetime.now(UTC),
                chat=Chat(id=CHAT_ID, type="supergroup", title="Test Chat"),
                from_user=User(id=REPORTER_ID, is_bot=False, first_name="Reporter"),
                text="/report",
                entities=[MessageEntity(type="bot_command", offset=0, length=7)],
            ),
        )

        await dispatcher.feed_update(bot, update)

        send_calls = fake_tg.get_calls("sendMessage")
        assert len(send_calls) >= 1
        # Should contain hint about replying
        sent_text = send_calls[0].params.get("text", "")
        assert "Ответьте" in sent_text or "reply" in sent_text.lower()

    async def test_report_forwards_to_admin(self, dispatcher: Dispatcher, bot: Bot, fake_tg: FakeTelegramServer):
        """Sending /report as reply should forward a summary to admin chat."""
        target_msg = Message(
            message_id=30,
            date=datetime.now(UTC),
            chat=Chat(id=CHAT_ID, type="supergroup", title="Test Chat"),
            from_user=User(id=TARGET_USER_ID, is_bot=False, first_name="Target", username="target_user"),
            text="Buy cheap diploma!!!",
        )

        update = Update(
            update_id=2,
            message=Message(
                message_id=50,
                date=datetime.now(UTC),
                chat=Chat(id=CHAT_ID, type="supergroup", title="Test Chat"),
                from_user=User(id=REPORTER_ID, is_bot=False, first_name="Reporter", username="reporter_user"),
                text="/report",
                entities=[MessageEntity(type="bot_command", offset=0, length=7)],
                reply_to_message=target_msg,
            ),
        )

        await dispatcher.feed_update(bot, update)

        # Should have sent summary to admin and acknowledgment in chat
        send_calls = fake_tg.get_calls("sendMessage")
        # At least: admin summary + chat acknowledgment
        assert len(send_calls) >= 2

        # Admin summary should contain report details
        admin_msg = next(
            (c for c in send_calls if str(c.params.get("chat_id", "")) == str(SUPER_ADMIN_ID)),
            None,
        )
        assert admin_msg is not None
        admin_text = admin_msg.params.get("text", "")
        assert "Report" in admin_text
        assert "Target" in admin_text or str(TARGET_USER_ID) in admin_text
        assert "t.me/" in admin_text  # chat and message links present
        assert "Перейти к сообщению" in admin_text

        # Chat acknowledgment
        chat_msg = next(
            (c for c in send_calls if str(c.params.get("chat_id", "")) == str(CHAT_ID)),
            None,
        )
        assert chat_msg is not None
        assert "Жалоба" in chat_msg.params.get("text", "")

    async def test_spam_command_forwards_to_admin(self, dispatcher: Dispatcher, bot: Bot, fake_tg: FakeTelegramServer):
        """The /spam command should also forward to admin."""
        target_msg = Message(
            message_id=31,
            date=datetime.now(UTC),
            chat=Chat(id=CHAT_ID, type="supergroup", title="Test Chat"),
            from_user=User(id=TARGET_USER_ID, is_bot=False, first_name="Target"),
            text="Spam message",
        )

        update = Update(
            update_id=3,
            message=Message(
                message_id=51,
                date=datetime.now(UTC),
                chat=Chat(id=CHAT_ID, type="supergroup", title="Test Chat"),
                from_user=User(id=REPORTER_ID, is_bot=False, first_name="Reporter"),
                text="/spam",
                entities=[MessageEntity(type="bot_command", offset=0, length=5)],
                reply_to_message=target_msg,
            ),
        )

        await dispatcher.feed_update(bot, update)

        send_calls = fake_tg.get_calls("sendMessage")
        # Admin summary should say SPAM
        admin_msg = next(
            (c for c in send_calls if str(c.params.get("chat_id", "")) == str(SUPER_ADMIN_ID)),
            None,
        )
        assert admin_msg is not None
        assert "SPAM" in admin_msg.params.get("text", "")


@pytest.mark.e2e
class TestEscalationCallback:
    """Tests for escalation inline button callbacks."""

    async def test_escalation_resolve_records_in_db(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        db_session_maker: async_sessionmaker[AsyncSession],
        fake_tg: FakeTelegramServer,
    ):
        """Admin clicking escalation button should resolve in DB and execute action."""
        from datetime import timedelta

        # Seed escalation using the shared session maker (same pool as handler)
        async with db_session_maker() as seed_session:
            escalation = AgentEscalation(
                chat_id=CHAT_ID,
                target_user_id=TARGET_USER_ID,
                suggested_action="mute",
                reason="Suspicious message",
                timeout_at=datetime.now(UTC) + timedelta(minutes=30),
                message_text="Buy cheap diploma!!!",
                admin_message_id=999,
                admin_chat_id=SUPER_ADMIN_ID,
            )
            seed_session.add(escalation)
            await seed_session.commit()
            await seed_session.refresh(escalation)
            esc_id = escalation.id

        # Simulate admin clicking "ban" button
        escalation_msg = Message(
            message_id=999,
            date=datetime.now(UTC),
            chat=Chat(id=SUPER_ADMIN_ID, type="private"),
            from_user=User(id=5145935834, is_bot=True, first_name="Bot"),
            text="Escalation details here",
        )

        update = Update(
            update_id=10,
            callback_query=CallbackQuery(
                id="cb_1",
                from_user=User(id=SUPER_ADMIN_ID, is_bot=False, first_name="Admin", username="super_admin"),
                chat_instance="12345",
                data=f"esc:{esc_id}:ban",
                message=escalation_msg,
            ),
        )

        # Mock AgentCore.execute_action to avoid real Telegram API calls
        with patch("app.moderation.agent.AgentCore") as MockAgentCore:
            mock_instance = MockAgentCore.return_value
            mock_instance.execute_action = AsyncMock()
            await dispatcher.feed_update(bot, update)

            # Verify action was executed
            mock_instance.execute_action.assert_called_once()
            call_args = mock_instance.execute_action.call_args
            assert call_args[0][0] == "ban"  # action

        # Verify DB was updated (fresh session to see committed data)
        async with db_session_maker() as verify_session:
            stmt = select(AgentEscalation).where(AgentEscalation.id == esc_id)
            result = await verify_session.execute(stmt)
            resolved = result.scalar_one_or_none()

            assert resolved is not None
            assert resolved.status == "resolved"
            assert resolved.resolved_action == "ban"
            assert resolved.resolved_by == SUPER_ADMIN_ID

    async def test_non_admin_cannot_resolve_escalation(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        db_session_maker: async_sessionmaker[AsyncSession],
        fake_tg: FakeTelegramServer,
    ):
        """Non-super-admin clicking button should be rejected."""
        from datetime import timedelta

        async with db_session_maker() as seed_session:
            escalation = AgentEscalation(
                chat_id=CHAT_ID,
                target_user_id=TARGET_USER_ID,
                suggested_action="mute",
                reason="Suspicious",
                timeout_at=datetime.now(UTC) + timedelta(minutes=30),
            )
            seed_session.add(escalation)
            await seed_session.commit()
            await seed_session.refresh(escalation)
            esc_id = escalation.id

        NON_ADMIN_ID = 999999999

        update = Update(
            update_id=11,
            callback_query=CallbackQuery(
                id="cb_2",
                from_user=User(id=NON_ADMIN_ID, is_bot=False, first_name="Random"),
                chat_instance="12345",
                data=f"esc:{esc_id}:ban",
                message=Message(
                    message_id=999,
                    date=datetime.now(UTC),
                    chat=Chat(id=NON_ADMIN_ID, type="private"),
                    from_user=User(id=5145935834, is_bot=True, first_name="Bot"),
                    text="Escalation",
                ),
            ),
        )

        await dispatcher.feed_update(bot, update)

        # Should NOT be resolved
        async with db_session_maker() as verify_session:
            stmt = select(AgentEscalation).where(AgentEscalation.id == esc_id)
            result = await verify_session.execute(stmt)
            esc = result.scalar_one()
            assert esc.status == "pending"

        # Should have answered with rejection
        answer_calls = fake_tg.get_calls("answerCallbackQuery")
        assert len(answer_calls) >= 1
        # Verify the answer contains a rejection message about admin-only access
        answer_text = answer_calls[0].params.get("text", "")
        assert "супер-админов" in answer_text or "admin" in answer_text.lower()
        assert answer_calls[0].params.get("show_alert") in (True, "true", "True")

    async def test_escalation_ignore_does_not_execute_action(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        db_session_maker: async_sessionmaker[AsyncSession],
        fake_tg: FakeTelegramServer,
    ):
        """Choosing 'ignore' should resolve but not execute any action."""
        from datetime import timedelta

        async with db_session_maker() as seed_session:
            escalation = AgentEscalation(
                chat_id=CHAT_ID,
                target_user_id=TARGET_USER_ID,
                suggested_action="mute",
                reason="Maybe spam",
                timeout_at=datetime.now(UTC) + timedelta(minutes=30),
            )
            seed_session.add(escalation)
            await seed_session.commit()
            await seed_session.refresh(escalation)
            esc_id = escalation.id

        update = Update(
            update_id=12,
            callback_query=CallbackQuery(
                id="cb_3",
                from_user=User(id=SUPER_ADMIN_ID, is_bot=False, first_name="Admin", username="admin"),
                chat_instance="12345",
                data=f"esc:{esc_id}:ignore",
                message=Message(
                    message_id=999,
                    date=datetime.now(UTC),
                    chat=Chat(id=SUPER_ADMIN_ID, type="private"),
                    from_user=User(id=5145935834, is_bot=True, first_name="Bot"),
                    text="Escalation",
                ),
            ),
        )

        # Mock AgentCore to verify it's NOT called for ignore
        with patch("app.moderation.agent.AgentCore") as MockAgentCore:
            mock_instance = MockAgentCore.return_value
            mock_instance.execute_action = AsyncMock()
            await dispatcher.feed_update(bot, update)

            # execute_action should NOT have been called for ignore
            mock_instance.execute_action.assert_not_called()

        # Should be resolved
        async with db_session_maker() as verify_session:
            stmt = select(AgentEscalation).where(AgentEscalation.id == esc_id)
            result = await verify_session.execute(stmt)
            esc = result.scalar_one()
            assert esc.status == "resolved"
            assert esc.resolved_action == "ignore"

    async def test_already_resolved_escalation_shows_error(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        db_session_maker: async_sessionmaker[AsyncSession],
        fake_tg: FakeTelegramServer,
    ):
        """Clicking a button on already-resolved escalation should notify user."""
        from datetime import timedelta

        async with db_session_maker() as seed_session:
            escalation = AgentEscalation(
                chat_id=CHAT_ID,
                target_user_id=TARGET_USER_ID,
                suggested_action="mute",
                reason="Old escalation",
                timeout_at=datetime.now(UTC) + timedelta(minutes=30),
            )
            escalation.status = "resolved"
            escalation.resolved_action = "ban"
            escalation.resolved_by = SUPER_ADMIN_ID
            seed_session.add(escalation)
            await seed_session.commit()
            await seed_session.refresh(escalation)

        update = Update(
            update_id=13,
            callback_query=CallbackQuery(
                id="cb_4",
                from_user=User(id=SUPER_ADMIN_ID, is_bot=False, first_name="Admin", username="admin"),
                chat_instance="12345",
                data=f"esc:{escalation.id}:mute",
                message=Message(
                    message_id=999,
                    date=datetime.now(UTC),
                    chat=Chat(id=SUPER_ADMIN_ID, type="private"),
                    from_user=User(id=5145935834, is_bot=True, first_name="Bot"),
                    text="Escalation",
                ),
            ),
        )

        await dispatcher.feed_update(bot, update)

        answer_calls = fake_tg.get_calls("answerCallbackQuery")
        assert len(answer_calls) >= 1
        # Verify the answer contains an error message about already-resolved escalation
        answer_text = answer_calls[0].params.get("text", "")
        assert "уже обработана" in answer_text or "already" in answer_text.lower()


@pytest.mark.e2e
class TestManagedChatsMiddleware:
    """Tests for the managed chats filtering."""

    async def test_unmanaged_chat_triggers_leave(
        self,
        bot: Bot,
        db_session_maker: async_sessionmaker[AsyncSession],
        fake_tg: FakeTelegramServer,
    ):
        """Bot should leave chats where no super admin is an admin."""
        UNMANAGED_CHAT_ID = -1009999999999
        fake_tg.set_chat_admins(UNMANAGED_CHAT_ID, [777777777])  # no super admin

        dp = Dispatcher()
        dp.update.middleware(DependenciesMiddleware(session_pool=db_session_maker, bot=bot))
        dp.update.middleware(ManagedChatsMiddleware())
        dp.include_router(_build_router())

        update = Update(
            update_id=20,
            message=Message(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=UNMANAGED_CHAT_ID, type="supergroup", title="Unmanaged"),
                from_user=User(id=111, is_bot=False, first_name="Random"),
                text="Hello",
            ),
        )

        await dp.feed_update(bot, update)

        leave_calls = fake_tg.get_calls("leaveChat")
        assert len(leave_calls) >= 1
        assert int(leave_calls[0].params["chat_id"]) == UNMANAGED_CHAT_ID
