"""AgentCore — PydanticAI-based moderation agent."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from aiogram import Bot, types
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agent.escalation import EscalationService
from app.agent.memory import AgentMemory
from app.agent.prompts import MODERATION_PROMPT
from app.agent.schemas import ActionType, AgentDeps, AgentEvent, ModerationResult
from app.core.config import settings
from app.core.logging import get_logger
from app.presentation.telegram.utils.other import escape_html

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("agent.core")


def _create_pydantic_agent() -> Agent[AgentDeps, ModerationResult]:
    """Create and configure the PydanticAI moderation agent."""
    provider = OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.agent.openrouter_api_key,
    )
    model = OpenAIModel(settings.agent.model, provider=provider)

    agent: Agent[AgentDeps, ModerationResult] = Agent(
        model,
        system_prompt=MODERATION_PROMPT,
        deps_type=AgentDeps,
        output_type=ModerationResult,
    )

    # --- Dynamic system prompt: inject admin correction patterns ---

    @agent.system_prompt
    async def add_correction_context(ctx: RunContext[AgentDeps]) -> str:
        """Inject recent admin corrections so the agent learns from feedback."""
        memory = AgentMemory(ctx.deps.db)
        corrections = await memory.get_recent_corrections(limit=5)
        if not corrections:
            return ""
        lines = ["## Recent admin corrections (learn from these):"]
        for c in corrections:
            lines.append(f"- Agent chose '{c.action}' but admin overrode to '{c.admin_override}'. Reason: {c.reason}")
        lines.append("\nAdjust your decisions based on these patterns.")
        return "\n".join(lines)

    # --- Tools (information-gathering, not actions) ---

    @agent.tool
    async def get_user_moderation_history(ctx: RunContext[AgentDeps]) -> str:
        """Check if this user has been reported or moderated before. Returns previous decisions including admin overrides."""
        memory = AgentMemory(ctx.deps.db)
        history = await memory.get_user_history(ctx.deps.event.target_user_id, limit=5)
        if not history:
            return "No previous moderation history for this user."
        lines = []
        for d in history:
            date_str = d.created_at.strftime("%Y-%m-%d") if d.created_at else "unknown"
            override = f" [ADMIN OVERRIDE → {d.admin_override}]" if d.admin_override else ""
            lines.append(f"- {d.action}: {d.reason} ({date_str}){override}")
        return "\n".join(lines)

    @agent.tool
    async def get_chat_recent_actions(ctx: RunContext[AgentDeps]) -> str:
        """Get recent moderation actions in this chat for context."""
        memory = AgentMemory(ctx.deps.db)
        history = await memory.get_chat_history(ctx.deps.event.chat_id, limit=5)
        if not history:
            return "No recent moderation actions in this chat."
        lines = []
        for d in history:
            date_str = d.created_at.strftime("%Y-%m-%d") if d.created_at else "unknown"
            override = f" [OVERRIDE → {d.admin_override}]" if d.admin_override else ""
            lines.append(f"- user {d.target_user_id}: {d.action} — {d.reason} ({date_str}){override}")
        return "\n".join(lines)

    @agent.tool
    async def get_user_risk_profile(ctx: RunContext[AgentDeps]) -> str:
        """Get aggregate risk profile for the reported user: total reports, distinct reporters, cross-chat activity, action history."""
        memory = AgentMemory(ctx.deps.db)
        profile = await memory.get_user_risk_profile(ctx.deps.event.target_user_id)

        if profile.total_reports == 0:
            return "No prior reports for this user — first-time report."

        lines = [
            f"Total reports: {profile.total_reports}",
            f"Distinct reporters: {profile.distinct_reporters}",
            f"Reported in {profile.distinct_chats} different chat(s)",
            f"Admin overrides: {profile.overridden_count}",
        ]
        if profile.actions_taken:
            breakdown = ", ".join(f"{k}: {v}" for k, v in profile.actions_taken.items())
            lines.append(f"Action breakdown: {breakdown}")
        if profile.last_action:
            lines.append(f"Last action: {profile.last_action}")
        return "\n".join(lines)

    @agent.tool
    async def get_admin_corrections(ctx: RunContext[AgentDeps]) -> str:
        """Get recent cases where admin overrode the agent's decision — use to calibrate your judgement."""
        memory = AgentMemory(ctx.deps.db)
        corrections = await memory.get_recent_corrections(limit=5)
        if not corrections:
            return "No admin corrections recorded yet."
        lines = []
        for c in corrections:
            date_str = c.created_at.strftime("%Y-%m-%d") if c.created_at else "unknown"
            lines.append(f"- Agent: {c.action} → Admin: {c.admin_override} | Reason: {c.reason} ({date_str})")
        return "\n".join(lines)

    return agent


class AgentCore:
    """Main agent — receives events, runs PydanticAI agent, executes actions."""

    def __init__(self) -> None:
        self._agent = _create_pydantic_agent()

    async def process_report(
        self,
        event: AgentEvent,
        bot: Bot,
        db: AsyncSession,
    ) -> ModerationResult:
        """Process a report/spam event end-to-end."""
        deps = AgentDeps(bot=bot, db=db, event=event)
        user_prompt = self._build_user_prompt(event)

        # Run PydanticAI agent
        try:
            result: AgentRunResult[ModerationResult] = await self._agent.run(user_prompt, deps=deps)
            decision = result.output
        except Exception as e:
            logger.error("Agent run failed", error=str(e))
            decision = ModerationResult(
                action="escalate",
                reason="Ошибка анализа: не удалось обработать запрос",
                suggested_action="ignore",
            )

        # Log to memory BEFORE execution so decision_id is available for escalation
        memory = AgentMemory(db)
        db_decision = await memory.log_decision(
            event=event,
            action=decision.action,
            reason=decision.reason,
        )

        # Execute the decided action (passes decision_id for escalation linkage)
        await self._execute(decision, event, bot, db, decision_id=db_decision.id)

        logger.info(
            "Agent decision",
            event_type=event.event_type,
            action=decision.action,
            chat_id=event.chat_id,
            target=event.target_user_id,
            decision_id=db_decision.id,
        )

        return decision

    def _build_user_prompt(self, event: AgentEvent) -> str:
        """Build the user message for the LLM."""
        parts = [
            f"Event type: {event.event_type}",
            f"Chat: {event.chat_title or event.chat_id}",
            f"Reported user: {event.target_display_name}"
            + (f" (@{event.target_username})" if event.target_username else ""),
            f"User ID: {event.target_user_id}",
        ]

        if event.target_message_text:
            parts.append(f"\nReported message:\n<user_message>\n{event.target_message_text}\n</user_message>")

        if event.context_messages:
            parts.append("\nRecent messages from this user in this chat:")
            for msg in event.context_messages[-5:]:
                parts.append(f"<user_message>{msg.get('text', '[no text]')}</user_message>")

        return "\n".join(parts)

    async def execute_action(
        self,
        action: str,
        event: AgentEvent,
        bot: Bot,
        db: AsyncSession,
        params: dict[str, str | int | bool | None] | None = None,
    ) -> None:
        """Execute a moderation action (used by escalation callbacks too)."""
        result = ModerationResult(
            action=action,
            reason="Admin decision",
            **(params or {}),
        )
        await self._execute(result, event, bot, db)

    async def _execute(
        self,
        decision: ModerationResult,
        event: AgentEvent,
        bot: Bot,
        db: AsyncSession,
        decision_id: int | None = None,
    ) -> None:
        """Execute the moderation action."""
        action = ActionType(decision.action)
        match action:
            case ActionType.MUTE:
                await self._do_mute(event, bot, decision.duration_minutes or 60)
            case ActionType.BAN:
                await self._do_ban(event, bot)
            case ActionType.DELETE:
                await self._do_delete(event, bot)
            case ActionType.WARN:
                await self._do_warn(event, bot, decision.warning_text)
            case ActionType.BLACKLIST:
                await self._do_blacklist(event, bot, db, decision.revoke_messages)
            case ActionType.ESCALATE:
                await self._do_escalate(event, bot, db, decision, decision_id)
            case ActionType.IGNORE:
                pass

    async def _do_mute(self, event: AgentEvent, bot: Bot, duration_minutes: int) -> None:
        permissions = types.ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
        )
        try:
            await bot.restrict_chat_member(
                event.chat_id,
                event.target_user_id,
                permissions=permissions,
                until_date=timedelta(minutes=duration_minutes),
            )
        except Exception as e:
            logger.error("Mute failed", error=str(e), user=event.target_user_id)

    async def _do_ban(self, event: AgentEvent, bot: Bot) -> None:
        try:
            await bot.ban_chat_member(event.chat_id, event.target_user_id)
        except Exception as e:
            logger.error("Ban failed", error=str(e), user=event.target_user_id)

    async def _do_delete(self, event: AgentEvent, bot: Bot) -> None:
        try:
            await bot.delete_message(event.chat_id, event.message_id)
        except Exception as e:
            logger.error("Delete failed", error=str(e), message=event.message_id)

    async def _do_warn(self, event: AgentEvent, bot: Bot, warning_text: str | None) -> None:
        text = warning_text or "Пожалуйста, соблюдайте правила чата."
        try:
            await bot.send_message(
                event.chat_id,
                f"⚠️ {escape_html(event.target_display_name)}, {escape_html(text)}",
                reply_to_message_id=event.message_id,
            )
        except Exception as e:
            logger.error("Warn failed", error=str(e), user=event.target_user_id)

    async def _do_blacklist(self, event: AgentEvent, bot: Bot, db: AsyncSession, revoke: bool) -> None:
        # Lazy import to avoid circular dependency (moderation → telegram.logger → bot → agent)
        from app.application.services import moderation as moderation_services

        try:
            await moderation_services.add_to_blacklist(db, bot, event.target_user_id, revoke_messages=revoke)
        except Exception as e:
            logger.error("Blacklist failed", error=str(e), user=event.target_user_id)

    async def _do_escalate(
        self,
        event: AgentEvent,
        bot: Bot,
        db: AsyncSession,
        decision: ModerationResult,
        decision_id: int | None = None,
    ) -> None:
        escalation_svc = EscalationService(bot, db)
        suggested = decision.suggested_action or "ignore"
        try:
            await escalation_svc.create(
                event=event,
                reason=decision.reason,
                suggested_action=suggested,
                decision_id=decision_id,
            )
        except Exception as e:
            logger.error("Escalation failed", error=str(e))
