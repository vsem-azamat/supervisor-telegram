"""Destructive actions proposed from outside, held until an admin presses.

Deliberately not an extension of :class:`EscalationService`. Half of that class
is about the moderation domain — an ``AgentEvent``, a suggested action, and a
timeout that *carries out* its default. That last part is the whole difference:
an escalation times out into action because the bot already judged something
wrong and wanted a second opinion, while a proposal from an external runtime
must time out into nothing.

Expiry here is a stored timestamp, checked when the action is read and swept in
the background — not an ``asyncio`` task in a module-level dict. A timer only
exists in the process that created it, so a proposal raised in one process and
confirmed in another would never expire; a timestamp survives both restarts and
process boundaries.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any, Protocol

from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update

from app.core.enums import PendingActionStatus
from app.core.logging import get_logger
from app.core.text import escape_html
from app.core.time import utc_now
from app.db.models import PendingAction
from app.presentation.telegram.utils.callback_data import PendingActionDecision

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("moderation.pending_actions")

DEFAULT_EXPIRY_MINUTES = 60

_ACTION_LABELS = {
    "ban": "забанить",
    "blacklist": "занести в чёрный список",
}


SWEEP_INTERVAL_SECONDS = 300


async def expire_stale(db: AsyncSession) -> int:
    """Mark everything past its deadline as expired. Executes nothing.

    A free function because expiry needs no bot: nothing is sent, nothing is
    carried out. The sweep can therefore run without a Telegram session at all.
    """
    now = utc_now()
    stale = (
        (
            await db.execute(
                select(PendingAction.id).where(
                    PendingAction.status == PendingActionStatus.PENDING,
                    PendingAction.expires_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    if not stale:
        return 0

    await db.execute(
        update(PendingAction)
        .where(PendingAction.id.in_(stale))
        .values(status=PendingActionStatus.EXPIRED, resolved_at=now)
    )
    await db.commit()
    logger.info("pending_actions_expired", count=len(stale))
    return len(stale)


class ActionExecutor(Protocol):
    """Carries out a confirmed action. Injected so tests need no live bot."""

    async def __call__(self, pending: PendingAction, bot: Bot, db: AsyncSession) -> None: ...


async def _execute(pending: PendingAction, bot: Bot, db: AsyncSession) -> None:
    """Run the action through the existing moderation executor.

    Reuses ``AgentCore.execute_action`` rather than reimplementing ban and
    blacklist, so both paths keep behaving the same way.
    """
    from app.moderation.agent import AgentCore
    from app.moderation.schemas import AgentEvent, EventType

    event = AgentEvent(
        event_type=EventType.REPORT,
        chat_id=pending.chat_id or 0,
        chat_title=None,
        message_id=0,
        # The admin who confirmed stands behind the action.
        reporter_id=pending.resolved_by or pending.initiator_id,
        target_user_id=pending.target_user_id,
        target_username=None,
        target_display_name=str(pending.target_user_id),
        target_message_text=None,
    )
    await AgentCore().execute_action(pending.action, event, bot, db, params=dict(pending.params or {}))


class PendingActionService:
    """Propose, confirm, reject and expire actions awaiting a human press."""

    def __init__(
        self,
        bot: Bot,
        db: AsyncSession,
        executor: ActionExecutor | None = None,
    ) -> None:
        self.bot = bot
        self.db = db
        self._execute = executor or _execute

    async def propose(
        self,
        *,
        origin: str,
        initiator_id: int,
        action: str,
        target_user_id: int,
        chat_id: int | None = None,
        params: dict[str, Any] | None = None,
        reason: str | None = None,
        expires_in_minutes: int = DEFAULT_EXPIRY_MINUTES,
    ) -> PendingAction:
        """Record the proposal and put it in front of the initiating admin."""
        pending = PendingAction(
            origin=origin,
            initiator_id=initiator_id,
            action=action,
            target_user_id=target_user_id,
            expires_at=utc_now() + datetime.timedelta(minutes=expires_in_minutes),
            chat_id=chat_id,
            params=params,
            reason=reason,
        )
        self.db.add(pending)
        await self.db.commit()
        await self.db.refresh(pending)

        message = await self.bot.send_message(
            chat_id=initiator_id,
            text=self._render(pending),
            reply_markup=self._keyboard(pending.id),
        )
        pending.admin_chat_id = initiator_id
        pending.admin_message_id = message.message_id
        await self.db.commit()

        logger.info(
            "pending_action_proposed",
            pending_id=pending.id,
            origin=origin,
            action=action,
            initiator_id=initiator_id,
            target_user_id=target_user_id,
        )
        return pending

    async def confirm(self, pending_id: int, admin_id: int) -> PendingAction | None:
        """Execute the action. Returns None if it is gone, taken or expired."""
        pending = await self._claim(pending_id)
        if pending is None:
            return None

        if pending.expires_at <= utc_now():
            await self._mark(pending, PendingActionStatus.EXPIRED, admin_id=None)
            logger.info("pending_action_expired_on_press", pending_id=pending_id)
            return None

        await self._mark(pending, PendingActionStatus.CONFIRMED, admin_id=admin_id)
        await self._execute(pending, self.bot, self.db)
        logger.info("pending_action_confirmed", pending_id=pending_id, admin_id=admin_id, action=pending.action)
        return pending

    async def reject(self, pending_id: int, admin_id: int) -> PendingAction | None:
        """Drop the proposal without executing anything."""
        pending = await self._claim(pending_id)
        if pending is None:
            return None

        await self._mark(pending, PendingActionStatus.REJECTED, admin_id=admin_id)
        logger.info("pending_action_rejected", pending_id=pending_id, admin_id=admin_id)
        return pending

    async def expire_stale(self) -> int:
        """Convenience wrapper for callers that already hold a service."""
        return await expire_stale(self.db)

    async def _claim(self, pending_id: int) -> PendingAction | None:
        """Fetch only while still pending, so a second press finds nothing."""
        result = await self.db.execute(
            select(PendingAction).where(
                PendingAction.id == pending_id,
                PendingAction.status == PendingActionStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def _mark(self, pending: PendingAction, status: PendingActionStatus, *, admin_id: int | None) -> None:
        pending.status = status
        pending.resolved_by = admin_id
        pending.resolved_at = utc_now()
        await self.db.commit()

    def _render(self, pending: PendingAction) -> str:
        label = _ACTION_LABELS.get(pending.action, pending.action)
        lines = [
            f"Запрошено действие: <b>{escape_html(label)}</b>",
            f"Пользователь: <code>{pending.target_user_id}</code>",
        ]
        if pending.chat_id is not None:
            lines.append(f"Чат: <code>{pending.chat_id}</code>")
        if pending.reason:
            lines.append(f"Причина: {escape_html(pending.reason)}")
        lines.append(f"Источник: <code>{escape_html(pending.origin)}</code>")
        lines.append("\nБез подтверждения ничего не произойдёт.")
        return "\n".join(lines)

    @staticmethod
    def _keyboard(pending_id: int):
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить", callback_data=PendingActionDecision(pending_id=pending_id, confirm=1))
        builder.button(text="✖️ Отклонить", callback_data=PendingActionDecision(pending_id=pending_id, confirm=0))
        builder.adjust(2)
        return builder.as_markup()


async def run_expiry_sweep(
    session_maker: async_sessionmaker[AsyncSession],
    interval_seconds: int = SWEEP_INTERVAL_SECONDS,
) -> None:
    """Periodically retire proposals nobody answered.

    Correctness does not depend on this — ``confirm`` refuses anything past its
    deadline on its own. The sweep is here so the stored status stops claiming
    a proposal is still awaiting an answer when it is not, including the ones
    left behind by a restart.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with session_maker() as session:
                await expire_stale(session)
        except asyncio.CancelledError:
            logger.info("pending_action_sweep_cancelled")
            raise
        except Exception:
            logger.exception("pending_action_sweep_failed")
