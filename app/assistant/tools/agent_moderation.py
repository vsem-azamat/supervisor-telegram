"""Agent moderation tool — wraps AgentCore for LLM-based moderation analysis.

This tool allows the assistant bot to analyze reported messages using the
PydanticAI moderation agent and execute moderation actions through the
moderator bot.
"""

from pydantic_ai import Agent, RunContext

from app.assistant.agent import AssistantDeps
from app.core.logging import get_logger

logger = get_logger("assistant.tools.agent_moderation")


def register_agent_moderation_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register LLM-based moderation analysis tools on the assistant agent."""

    @agent.tool
    async def analyze_message(
        ctx: RunContext[AssistantDeps],
        chat_id: int,
        message_id: int,
        target_user_id: int,
        target_display_name: str,
        message_text: str,
        chat_title: str = "",
        target_username: str = "",
        reporter_id: int = 0,
        event_type: str = "report",
    ) -> str:
        """Analyze a reported message using the AI moderation agent.

        This runs full LLM analysis on the message, checks user history,
        and returns a moderation decision with action and reason.

        Args:
            chat_id: The chat where the message was sent.
            message_id: The message ID being reported.
            target_user_id: User ID of the message author.
            target_display_name: Display name of the target user.
            message_text: Text content of the reported message.
            chat_title: Title of the chat (optional).
            target_username: Username of the target user without @ (optional).
            reporter_id: User ID who reported the message (optional).
            event_type: Either "report" or "spam".
        """
        from app.agent.core import AgentCore
        from app.agent.schemas import AgentEvent, EventType

        try:
            evt_type = EventType.SPAM if event_type == "spam" else EventType.REPORT
        except ValueError:
            evt_type = EventType.REPORT

        event = AgentEvent(
            event_type=evt_type,
            chat_id=chat_id,
            chat_title=chat_title or None,
            message_id=message_id,
            reporter_id=reporter_id,
            target_user_id=target_user_id,
            target_username=target_username or None,
            target_display_name=target_display_name,
            target_message_text=message_text,
        )

        try:
            agent_core = AgentCore()
            async with ctx.deps.session_maker() as session:
                decision = await agent_core.process_report(
                    event=event,
                    bot=ctx.deps.main_bot,
                    db=session,
                )

            lines = [
                "Moderation Analysis Result:",
                f"- Action: {decision.action}",
                f"- Reason: {decision.reason}",
            ]
            if decision.duration_minutes:
                lines.append(f"- Mute duration: {decision.duration_minutes} minutes")
            if decision.warning_text:
                lines.append(f"- Warning: {decision.warning_text}")
            if decision.suggested_action:
                lines.append(f"- Suggested action (for escalation): {decision.suggested_action}")
            return "\n".join(lines)

        except Exception:
            logger.exception("analyze_message_failed", chat_id=chat_id, user_id=target_user_id)
            return "Ошибка анализа сообщения. Проверьте логи."

    @agent.tool
    async def get_moderation_history(
        ctx: RunContext[AssistantDeps],
        user_id: int,
    ) -> str:
        """Get moderation history for a user — past reports, actions, admin overrides.

        Args:
            user_id: The user ID to look up.
        """
        from app.agent.memory import AgentMemory

        try:
            async with ctx.deps.session_maker() as session:
                memory = AgentMemory(session)
                profile = await memory.get_user_risk_profile(user_id)
                history = await memory.get_user_history(user_id, limit=10)

            if profile.total_reports == 0:
                return f"No moderation history for user {user_id}."

            lines = [
                f"Moderation Profile for user {user_id}:",
                f"- Total reports: {profile.total_reports}",
                f"- Distinct reporters: {profile.distinct_reporters}",
                f"- Active in {profile.distinct_chats} chat(s)",
                f"- Admin overrides: {profile.overridden_count}",
            ]
            if profile.actions_taken:
                breakdown = ", ".join(f"{k}: {v}" for k, v in profile.actions_taken.items())
                lines.append(f"- Actions: {breakdown}")
            if profile.last_action:
                lines.append(f"- Last action: {profile.last_action}")

            if history:
                lines.append("\nRecent decisions:")
                for d in history[:5]:
                    date_str = d.created_at.strftime("%Y-%m-%d") if d.created_at else "?"
                    override = f" [ADMIN: {d.admin_override}]" if d.admin_override else ""
                    lines.append(f"  - {d.action}: {d.reason} ({date_str}){override}")

            return "\n".join(lines)

        except Exception:
            logger.exception("get_moderation_history_failed", user_id=user_id)
            return "Ошибка получения истории модерации. Проверьте логи."
