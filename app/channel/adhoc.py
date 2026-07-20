"""Ad-hoc, operator-initiated post generation.

The scheduled Burr pipeline (:mod:`app.channel.workflow`) turns RSS items into
posts on a timer. This module covers the other entry point: an operator names a
topic and a post is generated immediately, then routed to the channel's review
chat — or published directly when the channel has no review chat, mirroring the
pipeline's ``send_for_review`` behaviour.

Two entry points call this: the assistant tool ``generate_and_review`` and the
MCP tool ``generate_and_send_for_review``. The business rules live here so the
two stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Literal

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.adhoc")

AdhocStatus = Literal[
    "empty_topic",
    "channel_not_found",
    "no_review_chat",
    "generation_failed",
    "generation_empty",
    "review_send_failed",
    "publish_failed",
    "sent_for_review",
    "published",
]

PREVIEW_CHARS = 300


@dataclass(frozen=True)
class AdhocResult:
    """Outcome of one ad-hoc generation request.

    ``status`` carries expected outcomes — including failures — so each caller
    renders them in its own format. Unexpected exceptions are logged here and
    collapsed into a failure status rather than propagated, because both entry
    points are agent-facing and must not surface tracebacks to an LLM.
    """

    status: AdhocStatus
    post_id: int | None = None
    message_id: int | None = None
    preview: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("sent_for_review", "published")


def _preview(text: str) -> str:
    return text[:PREVIEW_CHARS] + ("..." if len(text) > PREVIEW_CHARS else "")


async def generate_for_review(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    review_bot: Bot,
    channel_id: int,
    topic: str,
    source_url: str = "",
    publish_bot: Bot | None = None,
) -> AdhocResult:
    """Generate a post for *channel_id* from *topic* and route it for review.

    ``review_bot`` sends the review message and therefore owns its inline-keyboard
    callbacks: it must be the same bot identity whose dispatcher has
    ``channel_review_router`` attached, otherwise the approve/reject buttons are
    delivered to a bot that cannot handle them.

    ``publish_bot`` is the capability to publish without review, used only when
    the channel has no review chat. Omitting it makes that path structurally
    unreachable — the call returns ``no_review_chat`` instead. Callers that must
    never publish (the MCP endpoint) simply do not pass one, so the guarantee
    does not depend on them checking ``review_chat_id`` beforehand and cannot be
    defeated by the channel changing between that check and this call.

    The channel must exist in the ``channels`` table; an unknown ``channel_id``
    is rejected before any LLM call or Telegram send.
    """
    from app.channel.channel_repo import get_channel_by_telegram_id
    from app.channel.config import language_name
    from app.channel.generator import generate_post
    from app.channel.sources import ContentItem
    from app.core.config import settings

    if not topic.strip():
        return AdhocResult(status="empty_topic")

    channel = await get_channel_by_telegram_id(session_maker, channel_id)
    if channel is None:
        return AdhocResult(status="channel_not_found")

    # Decide routing from this single read, before spending an LLM call: a caller
    # with no publish capability cannot be served by a channel that lacks review.
    if not channel.review_chat_id and publish_bot is None:
        return AdhocResult(status="no_review_chat")

    external_id = sha256(f"{channel_id}:{topic[:100]}".encode()).hexdigest()[:16]
    item = ContentItem(
        source_url=source_url or "assistant",
        external_id=external_id,
        title=topic[:200],
        body=topic,
        url=source_url or None,
    )

    api_key = settings.openrouter.api_key
    channel_context = f"Channel focus: {channel.discovery_query}" if channel.discovery_query else ""

    try:
        post = await generate_post(
            [item],
            api_key=api_key,
            model=settings.channel.generation_model,
            language=language_name(channel.language),
            footer=channel.footer,
            channel_name=channel.name,
            channel_context=channel_context,
            channel_id=channel_id,
            session_maker=session_maker,
            vision_model=settings.channel.vision_model,
            phash_threshold=settings.channel.image_phash_threshold,
            phash_lookback=settings.channel.image_phash_lookback_posts,
        )
    except Exception:
        # GenerationError and transport failures alike: both entry points are
        # agent-facing, so failures become a status rather than a traceback.
        logger.exception("adhoc_generate_failed", channel_id=channel_id)
        return AdhocResult(status="generation_failed")

    if not post:
        return AdhocResult(status="generation_empty")

    if channel.review_chat_id:
        from app.channel.review import send_for_review

        try:
            post_id = await send_for_review(
                bot=review_bot,
                review_chat_id=channel.review_chat_id,
                channel_id=channel_id,
                post=post,
                source_items=[item],
                session_maker=session_maker,
                api_key=api_key,
                embedding_model=settings.channel.embedding_model,
                channel_name=channel.name,
                channel_username=channel.username,
            )
        except Exception:
            logger.exception("adhoc_review_send_failed", channel_id=channel_id)
            return AdhocResult(status="review_send_failed")

        if not post_id:
            return AdhocResult(status="review_send_failed")
        return AdhocResult(status="sent_for_review", post_id=post_id, preview=_preview(post.text))

    if publish_bot is None:
        # Unreachable via the early guard above; kept so the invariant holds at
        # the branch that would actually publish.
        return AdhocResult(status="no_review_chat")

    from app.channel.publisher import publish_post

    try:
        message_id = await publish_post(publish_bot, channel.telegram_id, post)
    except Exception:
        logger.exception("adhoc_publish_failed", channel_id=channel_id)
        return AdhocResult(status="publish_failed")

    if not message_id:
        return AdhocResult(status="publish_failed")
    return AdhocResult(status="published", message_id=message_id, preview=_preview(post.text))
