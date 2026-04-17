"""Unit tests for EscalationService."""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest
import pytest_asyncio
from aiogram import Bot
from app.infrastructure.db.models import AgentEscalation
from app.moderation.escalation import EscalationService, _timeout_tasks
from app.moderation.schemas import AgentEvent, EventType
from sqlalchemy import select

# ---- Fixtures ----


@pytest_asyncio.fixture()
async def db_session(db_session_maker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    async with db_session_maker() as session:
        yield session


@pytest.fixture(autouse=True)
def clear_timeout_tasks():
    """Clear global timeout tasks dict before and after each test."""
    _timeout_tasks.clear()
    yield
    # Cancel any remaining tasks
    for task in _timeout_tasks.values():
        if not task.done():
            task.cancel()
    _timeout_tasks.clear()


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock(spec=Bot)
    # send_message returns a message-like object with message_id
    msg = AsyncMock()
    msg.message_id = 999
    bot.send_message.return_value = msg
    return bot


@pytest.fixture
def sample_event() -> AgentEvent:
    return AgentEvent(
        event_type=EventType.REPORT,
        chat_id=-1001234567890,
        chat_title="Test Chat",
        message_id=42,
        reporter_id=111111111,
        target_user_id=222222222,
        target_username="target_user",
        target_display_name="Target User",
        target_message_text="Buy cheap diploma!",
    )


def _make_service(bot: AsyncMock, session: AsyncSession) -> EscalationService:
    return EscalationService(bot=bot, db=session)


# ---- Tests: create ----


@pytest.mark.unit
class TestEscalationCreate:
    async def test_create_stores_escalation_in_db(
        self,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        sample_event: AgentEvent,
    ):
        with patch("app.moderation.escalation.settings") as mock_settings:
            mock_settings.moderation.escalation_timeout_minutes = 30
            mock_settings.moderation.default_timeout_action = "ignore"
            mock_settings.admin.super_admins = [123456789]

            svc = _make_service(mock_bot, db_session)
            esc = await svc.create(sample_event, reason="spam", suggested_action="mute")

        assert esc.id is not None
        assert esc.chat_id == sample_event.chat_id
        assert esc.target_user_id == sample_event.target_user_id
        assert esc.suggested_action == "mute"
        assert esc.reason == "spam"
        assert esc.status == "pending"

        # Verify it's actually in DB
        stmt = select(AgentEscalation).where(AgentEscalation.id == esc.id)
        result = await db_session.execute(stmt)
        row = result.scalar_one()
        assert row.reason == "spam"

    async def test_create_sends_message_to_super_admin(
        self,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        sample_event: AgentEvent,
    ):
        with patch("app.moderation.escalation.settings") as mock_settings:
            mock_settings.moderation.escalation_timeout_minutes = 30
            mock_settings.moderation.default_timeout_action = "ignore"
            mock_settings.admin.super_admins = [123456789]

            svc = _make_service(mock_bot, db_session)
            await svc.create(sample_event, reason="spam", suggested_action="mute")

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[0][0] == 123456789  # admin_chat_id

    async def test_create_starts_timeout_task(
        self,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        sample_event: AgentEvent,
    ):
        with patch("app.moderation.escalation.settings") as mock_settings:
            mock_settings.moderation.escalation_timeout_minutes = 30
            mock_settings.moderation.default_timeout_action = "ignore"
            mock_settings.admin.super_admins = [123456789]

            svc = _make_service(mock_bot, db_session)
            esc = await svc.create(sample_event, reason="spam", suggested_action="mute")

        assert esc.id in _timeout_tasks
        task = _timeout_tasks[esc.id]
        assert isinstance(task, asyncio.Task)
        assert not task.done()

    async def test_create_no_super_admins_returns_early(
        self,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        sample_event: AgentEvent,
    ):
        with patch("app.moderation.escalation.settings") as mock_settings:
            mock_settings.moderation.escalation_timeout_minutes = 30
            mock_settings.moderation.default_timeout_action = "ignore"
            mock_settings.admin.super_admins = []

            svc = _make_service(mock_bot, db_session)
            esc = await svc.create(sample_event, reason="spam", suggested_action="mute")

        # Escalation is stored in DB but no message sent, no timeout task
        assert esc.id is not None
        mock_bot.send_message.assert_not_called()
        assert esc.id not in _timeout_tasks


# ---- Tests: resolve ----


@pytest.mark.unit
class TestEscalationResolve:
    async def _seed_escalation(self, session: AsyncSession, status: str = "pending") -> AgentEscalation:
        esc = AgentEscalation(
            chat_id=-1001234567890,
            target_user_id=222222222,
            suggested_action="mute",
            reason="test",
            timeout_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
        )
        esc.status = status
        session.add(esc)
        await session.commit()
        await session.refresh(esc)
        return esc

    async def test_resolve_pending_escalation(self, mock_bot: AsyncMock, db_session: AsyncSession):
        esc = await self._seed_escalation(db_session)
        svc = _make_service(mock_bot, db_session)

        resolved = await svc.resolve(esc.id, admin_id=123456789, action="ban")

        assert resolved is not None
        assert resolved.status == "resolved"
        assert resolved.resolved_action == "ban"
        assert resolved.resolved_by == 123456789
        assert resolved.resolved_at is not None

    async def test_resolve_already_resolved_returns_none(self, mock_bot: AsyncMock, db_session: AsyncSession):
        esc = await self._seed_escalation(db_session, status="resolved")
        svc = _make_service(mock_bot, db_session)

        result = await svc.resolve(esc.id, admin_id=123456789, action="ban")
        assert result is None

    async def test_resolve_cancels_timeout_task(self, mock_bot: AsyncMock, db_session: AsyncSession):
        esc = await self._seed_escalation(db_session)

        # Simulate a pending timeout task
        dummy_task = asyncio.create_task(asyncio.sleep(9999))
        _timeout_tasks[esc.id] = dummy_task

        svc = _make_service(mock_bot, db_session)
        await svc.resolve(esc.id, admin_id=123456789, action="ban")

        assert esc.id not in _timeout_tasks
        # Let event loop process the cancellation
        await asyncio.sleep(0)
        assert dummy_task.cancelled()


# ---- Tests: get_pending ----


@pytest.mark.unit
class TestGetPending:
    async def test_get_pending_returns_none_for_resolved(self, mock_bot: AsyncMock, db_session: AsyncSession):
        esc = AgentEscalation(
            chat_id=-100123,
            target_user_id=222,
            suggested_action="mute",
            reason="test",
            timeout_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
        )
        esc.status = "resolved"
        db_session.add(esc)
        await db_session.commit()
        await db_session.refresh(esc)

        svc = _make_service(mock_bot, db_session)
        result = await svc.get_pending(esc.id)
        assert result is None


# ---- Tests: timeout handler ----


@pytest.mark.unit
class TestTimeoutHandler:
    @patch("app.moderation.escalation.settings")
    async def test_timeout_handler_marks_timeout_status(
        self,
        mock_settings: object,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        mock_settings.moderation.default_timeout_action = "ignore"  # type: ignore[attr-defined]

        esc = AgentEscalation(
            chat_id=-100123,
            target_user_id=222,
            suggested_action="mute",
            reason="test",
            timeout_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
        )
        db_session.add(esc)
        await db_session.commit()
        await db_session.refresh(esc)

        EscalationService.set_session_maker(db_session_maker)
        svc = _make_service(mock_bot, db_session)

        # Call _timeout_handler with 0 sleep time
        with patch("app.moderation.escalation.asyncio.sleep", new_callable=AsyncMock):
            await svc._timeout_handler(esc.id, 0)

        # Verify in DB via fresh session
        async with db_session_maker() as verify_session:
            stmt = select(AgentEscalation).where(AgentEscalation.id == esc.id)
            result = await verify_session.execute(stmt)
            row = result.scalar_one()
            assert row.status == "timeout"
            assert row.resolved_action == "ignore"
            assert row.resolved_at is not None

    async def test_timeout_handler_no_session_maker_does_not_crash(
        self,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
    ):
        """When _session_maker is None, handler logs error but doesn't crash."""
        old_maker = EscalationService._session_maker
        EscalationService._session_maker = None
        try:
            svc = _make_service(mock_bot, db_session)
            with patch("app.moderation.escalation.asyncio.sleep", new_callable=AsyncMock):
                # Should not raise
                await svc._timeout_handler(999, 0)
        finally:
            EscalationService._session_maker = old_maker

    @patch("app.moderation.escalation.settings")
    async def test_timeout_handler_writes_memory_override_when_decision_id_set(
        self,
        mock_settings: object,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        mock_settings.moderation.default_timeout_action = "ignore"  # type: ignore[attr-defined]

        esc = AgentEscalation(
            chat_id=-100123,
            target_user_id=222,
            suggested_action="mute",
            reason="test",
            timeout_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30),
            decision_id=42,
        )
        db_session.add(esc)
        await db_session.commit()
        await db_session.refresh(esc)

        EscalationService.set_session_maker(db_session_maker)
        svc = _make_service(mock_bot, db_session)

        with (
            patch("app.moderation.escalation.asyncio.sleep", new_callable=AsyncMock),
            patch("app.moderation.memory.AgentMemory.set_admin_override", new_callable=AsyncMock) as mock_override,
        ):
            await svc._timeout_handler(esc.id, 0)

        mock_override.assert_called_once_with(42, "timeout:ignore")


# ---- Tests: recover_stale_escalations ----


@pytest.mark.unit
class TestRecoverStale:
    @patch("app.moderation.escalation.settings")
    async def test_recover_stale_escalations_marks_timed_out(
        self,
        mock_settings: object,
        db_session: AsyncSession,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        mock_settings.moderation.default_timeout_action = "ignore"  # type: ignore[attr-defined]

        # Insert a stale escalation (timeout_at in the past)
        esc = AgentEscalation(
            chat_id=-100123,
            target_user_id=222,
            suggested_action="mute",
            reason="stale",
            timeout_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5),
        )
        db_session.add(esc)
        await db_session.commit()
        await db_session.refresh(esc)

        await EscalationService.recover_stale_escalations(db_session_maker)

        async with db_session_maker() as verify_session:
            stmt = select(AgentEscalation).where(AgentEscalation.id == esc.id)
            result = await verify_session.execute(stmt)
            row = result.scalar_one()
            assert row.status == "timeout"
            assert row.resolved_action == "ignore"


# ---- Tests: _send_escalation_message formatting ----


@pytest.mark.unit
class TestSendEscalationMessage:
    @patch("app.moderation.escalation.settings")
    async def test_send_escalation_message_truncates_long_text(
        self,
        mock_settings: object,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
    ):
        mock_settings.moderation.escalation_timeout_minutes = 30  # type: ignore[attr-defined]
        mock_settings.moderation.default_timeout_action = "ignore"  # type: ignore[attr-defined]
        mock_settings.admin.super_admins = [123456789]  # type: ignore[attr-defined]

        long_text = "A" * 1000
        event = AgentEvent(
            event_type=EventType.REPORT,
            chat_id=-100123,
            chat_title="Test Chat",
            message_id=42,
            reporter_id=111,
            target_user_id=222,
            target_username="user",
            target_display_name="User",
            target_message_text=long_text,
        )

        svc = _make_service(mock_bot, db_session)
        await svc.create(event, reason="test", suggested_action="mute")

        sent_text = mock_bot.send_message.call_args[0][1]
        # The original 1000-char text should be truncated to 500 + "..."
        assert "..." in sent_text
        assert "A" * 501 not in sent_text

    @patch("app.moderation.escalation.settings")
    async def test_send_escalation_message_format_no_username(
        self,
        mock_settings: object,
        mock_bot: AsyncMock,
        db_session: AsyncSession,
    ):
        mock_settings.moderation.escalation_timeout_minutes = 30  # type: ignore[attr-defined]
        mock_settings.moderation.default_timeout_action = "ignore"  # type: ignore[attr-defined]
        mock_settings.admin.super_admins = [123456789]  # type: ignore[attr-defined]

        event = AgentEvent(
            event_type=EventType.REPORT,
            chat_id=-100123,
            chat_title=None,
            message_id=42,
            reporter_id=111,
            target_user_id=222,
            target_username=None,
            target_display_name="NoUsername User",
            target_message_text="test message",
        )

        svc = _make_service(mock_bot, db_session)
        await svc.create(event, reason="test", suggested_action="warn")

        sent_text = mock_bot.send_message.call_args[0][1]
        # No @username part
        assert "(@" not in sent_text
        # Chat shows as numeric ID since chat_title is None
        assert str(event.chat_id) in sent_text
        # Display name present
        assert "NoUsername User" in sent_text
