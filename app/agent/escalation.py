"""Escalation service — sends decisions to admin for review."""

import asyncio
import datetime

from aiogram import Bot
from aiogram.types import Message as TgMessage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.schemas import AgentEvent
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.models import AgentEscalation

logger = get_logger("agent.escalation")

# Global registry of timeout tasks so they can be cancelled
_timeout_tasks: dict[int, asyncio.Task[None]] = {}


class EscalationService:
    """Manages escalations to super admin."""

    # Session maker for background tasks (set once at startup)
    _session_maker: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def set_session_maker(cls, session_maker: async_sessionmaker[AsyncSession]) -> None:
        """Set the session maker for background tasks (called at bot startup)."""
        cls._session_maker = session_maker

    def __init__(self, bot: Bot, db: AsyncSession) -> None:
        self.bot = bot
        self.db = db

    async def create(
        self,
        event: AgentEvent,
        reason: str,
        suggested_action: str,
        decision_id: int | None = None,
    ) -> AgentEscalation:
        """Create escalation, send to admin, start timeout."""
        timeout_minutes = settings.agent.escalation_timeout_minutes
        # NOTE: DB columns are stored as TIMESTAMP WITHOUT TIME ZONE (naive).
        # Use naive UTC datetimes consistently to avoid asyncpg "offset-naive and offset-aware" errors.
        timeout_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=timeout_minutes)

        escalation = AgentEscalation(
            chat_id=event.chat_id,
            target_user_id=event.target_user_id,
            message_text=event.target_message_text,
            suggested_action=suggested_action,
            reason=reason,
            timeout_at=timeout_at,
            decision_id=decision_id,
        )
        self.db.add(escalation)
        await self.db.commit()
        await self.db.refresh(escalation)

        # Send to first super admin
        if not settings.admin.super_admins:
            logger.error("No super admins configured, cannot send escalation")
            return escalation

        admin_chat_id = settings.admin.super_admins[0]
        message = await self._send_escalation_message(escalation, event, admin_chat_id)

        escalation.admin_message_id = message.message_id
        escalation.admin_chat_id = admin_chat_id
        await self.db.commit()

        # Start timeout task
        task = asyncio.create_task(self._timeout_handler(escalation.id, timeout_minutes * 60))
        _timeout_tasks[escalation.id] = task

        logger.info(
            "Escalation created",
            escalation_id=escalation.id,
            target_user=event.target_user_id,
            suggested=suggested_action,
        )
        return escalation

    async def resolve(
        self,
        escalation_id: int,
        admin_id: int,
        action: str,
    ) -> AgentEscalation | None:
        """Resolve an escalation with admin's chosen action."""
        stmt = select(AgentEscalation).where(
            AgentEscalation.id == escalation_id,
            AgentEscalation.status == "pending",
        )
        result = await self.db.execute(stmt)
        escalation = result.scalar_one_or_none()

        if not escalation:
            return None

        escalation.status = "resolved"
        escalation.resolved_action = action
        escalation.resolved_by = admin_id
        escalation.resolved_at = datetime.datetime.utcnow()
        await self.db.commit()

        # Cancel timeout task
        task = _timeout_tasks.pop(escalation_id, None)
        if task and not task.done():
            task.cancel()

        logger.info(
            "Escalation resolved",
            escalation_id=escalation_id,
            action=action,
            admin_id=admin_id,
        )
        return escalation

    async def get_pending(self, escalation_id: int) -> AgentEscalation | None:
        """Get a pending escalation by ID."""
        stmt = select(AgentEscalation).where(
            AgentEscalation.id == escalation_id,
            AgentEscalation.status == "pending",
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def recover_stale_escalations(cls, session_maker: async_sessionmaker[AsyncSession]) -> None:
        """On startup, mark stale pending escalations as timed out."""
        async with session_maker() as db:
            now = datetime.datetime.utcnow()
            stmt = select(AgentEscalation).where(
                AgentEscalation.status == "pending",
                AgentEscalation.timeout_at < now,
            )
            result = await db.execute(stmt)
            stale = result.scalars().all()

            for esc in stale:
                esc.status = "timeout"
                esc.resolved_action = settings.agent.default_timeout_action
                esc.resolved_at = now
            if stale:
                await db.commit()
                logger.info("Recovered stale escalations", count=len(stale))

    async def _send_escalation_message(
        self,
        escalation: AgentEscalation,
        event: AgentEvent,
        admin_chat_id: int,
    ) -> TgMessage:
        """Send formatted escalation message to admin with action buttons."""
        text = (
            f"🚨 <b>Модерация: требуется решение</b>\n\n"
            f"📝 Событие: <code>{event.event_type}</code>\n"
            f"💬 Чат: {event.chat_title or event.chat_id}\n"
            f"👤 Пользователь: {event.target_display_name}"
            f"{f' (@{event.target_username})' if event.target_username else ''}\n"
            f"🆔 ID: <code>{event.target_user_id}</code>\n\n"
        )

        if event.target_message_text:
            truncated = event.target_message_text[:500]
            if len(event.target_message_text) > 500:
                truncated += "..."
            text += f"📄 Сообщение:\n<blockquote>{truncated}</blockquote>\n\n"

        text += (
            f"🤖 Предложение: <b>{escalation.suggested_action}</b>\n"
            f"💭 Причина: {escalation.reason}\n\n"
            f"⏰ Таймаут: {settings.agent.escalation_timeout_minutes} мин "
            f"→ <i>{settings.agent.default_timeout_action}</i>"
        )

        builder = InlineKeyboardBuilder()
        actions = [
            ("🔇 Мут", "mute"),
            ("🚫 Бан", "ban"),
            ("🗑 Удалить", "delete"),
            ("⚠️ Предупр.", "warn"),
            ("☠️ Черный список", "blacklist"),
            ("✅ Игнор", "ignore"),
        ]
        for label, action in actions:
            builder.button(
                text=label,
                callback_data=f"esc:{escalation.id}:{action}",
            )
        builder.adjust(3, 3)

        return await self.bot.send_message(admin_chat_id, text, reply_markup=builder.as_markup())

    async def _timeout_handler(self, escalation_id: int, timeout_seconds: int) -> None:
        """Handle escalation timeout — uses its own DB session to avoid stale session issues."""
        try:
            await asyncio.sleep(timeout_seconds)
        except asyncio.CancelledError:
            return

        logger.info("Escalation timed out", escalation_id=escalation_id)

        if not self._session_maker:
            logger.error("No session maker configured for timeout handler")
            return

        async with self._session_maker() as db:
            stmt = select(AgentEscalation).where(
                AgentEscalation.id == escalation_id,
                AgentEscalation.status == "pending",
            )
            result = await db.execute(stmt)
            escalation = result.scalar_one_or_none()

            if not escalation:
                return

            default_action = settings.agent.default_timeout_action
            escalation.status = "timeout"
            escalation.resolved_action = default_action
            escalation.resolved_at = datetime.datetime.utcnow()
            await db.commit()

            # Log timeout outcome as an admin override on the original decision
            if escalation.decision_id:
                from app.agent.memory import AgentMemory

                memory = AgentMemory(db)
                await memory.set_admin_override(escalation.decision_id, f"timeout:{default_action}")

        _timeout_tasks.pop(escalation_id, None)

        # Notify admin
        if escalation.admin_chat_id and escalation.admin_message_id:
            try:
                await self.bot.send_message(
                    escalation.admin_chat_id,
                    f"⏰ Эскалация #{escalation_id} истекла. Действие: <b>{default_action}</b>",
                    reply_to_message_id=escalation.admin_message_id,
                )
            except Exception as e:
                logger.warning("Failed to send timeout notification", error=str(e))
