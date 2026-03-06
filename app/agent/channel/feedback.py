"""Feedback memory — summarizes admin preferences to improve future generations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.agent.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger
from app.infrastructure.db.models import ChannelPost, ChannelSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.feedback")


async def get_feedback_summary(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
    api_key: str,
    model: str,
    *,
    http_timeout: int = 30,
    temperature: float = 0.2,
) -> str | None:
    """Summarize admin feedback patterns for a channel.

    Analyzes approved/rejected posts and source health to produce
    a summary the generation agent can use as context.
    """
    async with session_maker() as session:
        # Get recent posts with their statuses
        posts_result = await session.execute(
            select(ChannelPost)
            .where(ChannelPost.channel_id == channel_id, ChannelPost.status.in_(["approved", "rejected"]))
            .order_by(ChannelPost.created_at.desc())
            .limit(20)
        )
        posts = list(posts_result.scalars().all())

        # Get source stats
        sources_result = await session.execute(select(ChannelSource).where(ChannelSource.channel_id == channel_id))
        sources = list(sources_result.scalars().all())

    if not posts:
        return None

    # Build context for summarization
    approved = [p for p in posts if p.status == "approved"]
    rejected = [p for p in posts if p.status == "rejected"]

    context_parts = [
        f"Channel: {channel_id}",
        f"Total recent posts: {len(posts)} ({len(approved)} approved, {len(rejected)} rejected)",
    ]

    if approved:
        context_parts.append("\nApproved post titles:")
        for p in approved[:10]:
            context_parts.append(f"  - {p.title[:80]}")

    if rejected:
        context_parts.append("\nRejected post titles:")
        for p in rejected[:10]:
            feedback = f" (feedback: {p.admin_feedback})" if p.admin_feedback else ""
            context_parts.append(f"  - {p.title[:80]}{feedback}")

    if sources:
        active = [s for s in sources if s.enabled]
        disabled = [s for s in sources if not s.enabled]
        context_parts.append(f"\nSources: {len(active)} active, {len(disabled)} disabled")
        for s in disabled:
            context_parts.append(f"  Disabled: {s.url} (errors: {s.error_count}, last: {s.last_error})")

    context = "\n".join(context_parts)

    # Ask LLM to summarize
    try:
        summary = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize the admin's content preferences in 3-5 bullet points. "
                        "What topics do they approve? What do they reject? "
                        "What patterns do you see? Keep it concise."
                    ),
                },
                {"role": "user", "content": context},
            ],
            operation="feedback",
            channel_id=channel_id,
            temperature=temperature,
            timeout=http_timeout,
            strip_code_fences=False,
        )
        if summary:
            logger.info("feedback_summarized", channel_id=channel_id, length=len(summary))
        return summary

    except Exception:
        logger.exception("feedback_summary_error")
        return None
