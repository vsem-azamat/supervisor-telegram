"""Ad-hoc generation service: topic in, review draft (or direct publish) out.

Covers the branches the assistant tool exercised but never had tests for, and
pins the bot-identity split: review drafts must go out via the review bot, direct
publishes via the publish bot.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.adhoc import PREVIEW_CHARS, generate_for_review
from app.db.models import Channel

pytestmark = pytest.mark.asyncio

CHANNEL_ID = -1001234567890


async def _add_channel(session_maker, *, review_chat_id: int | None) -> None:
    async with session_maker() as session:
        session.add(
            Channel(
                telegram_id=CHANNEL_ID,
                name="Test Channel",
                language="ru",
                review_chat_id=review_chat_id,
            )
        )
        await session.commit()


def _post(text: str = "Generated body"):
    return SimpleNamespace(text=text, image_url=None, image_urls=[])


async def _run(session_maker, **overrides):
    kwargs = {
        "session_maker": session_maker,
        "review_bot": AsyncMock(),
        "publish_bot": AsyncMock(),
        "channel_id": CHANNEL_ID,
        "topic": "A full news story with facts and context",
        "source_url": "https://example.com/article",
    }
    kwargs.update(overrides)
    return await generate_for_review(**kwargs)


async def test_empty_topic_rejected_before_generation(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)

    with patch("app.channel.generator.generate_post", new=AsyncMock()) as generate:
        result = await _run(session_maker, topic="   ")

    assert result.status == "empty_topic"
    assert not result.ok
    generate.assert_not_awaited()


async def test_unknown_channel_rejected_before_generation(session_maker) -> None:
    with patch("app.channel.generator.generate_post", new=AsyncMock()) as generate:
        result = await _run(session_maker, channel_id=-1009999999999)

    assert result.status == "channel_not_found"
    generate.assert_not_awaited()


async def test_review_draft_goes_out_via_review_bot(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)
    review_bot, publish_bot = AsyncMock(), AsyncMock()

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock(return_value=_post())),
        patch("app.channel.review.send_for_review", new=AsyncMock(return_value=77)) as send,
        patch("app.channel.publisher.publish_post", new=AsyncMock()) as publish,
    ):
        result = await _run(session_maker, review_bot=review_bot, publish_bot=publish_bot)

    assert result.status == "sent_for_review"
    assert result.ok
    assert result.post_id == 77
    assert result.message_id is None
    publish.assert_not_awaited()
    # The bot that sends the review message owns its inline-keyboard callbacks.
    assert send.await_args is not None
    assert send.await_args.kwargs["bot"] is review_bot
    assert send.await_args.kwargs["review_chat_id"] == -100500


async def test_channel_without_review_chat_publishes_via_publish_bot(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=None)
    review_bot, publish_bot = AsyncMock(), AsyncMock()

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock(return_value=_post())),
        patch("app.channel.review.send_for_review", new=AsyncMock()) as send,
        patch("app.channel.publisher.publish_post", new=AsyncMock(return_value=4242)) as publish,
    ):
        result = await _run(session_maker, review_bot=review_bot, publish_bot=publish_bot)

    assert result.status == "published"
    assert result.message_id == 4242
    assert result.post_id is None
    send.assert_not_awaited()
    assert publish.await_args is not None
    assert publish.await_args.args[0] is publish_bot


async def test_without_publish_bot_the_direct_publish_path_is_unreachable(session_maker) -> None:
    """Omitting publish_bot is the capability check that keeps callers read-only.

    The MCP endpoint relies on this: it must not be able to publish even when the
    channel has no review chat, and that must not depend on the caller checking
    review_chat_id first.
    """
    await _add_channel(session_maker, review_chat_id=None)

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock()) as generate,
        patch("app.channel.publisher.publish_post", new=AsyncMock()) as publish,
    ):
        result = await generate_for_review(
            session_maker=session_maker,
            review_bot=AsyncMock(),
            channel_id=CHANNEL_ID,
            topic="A full news story with facts and context",
        )

    assert result.status == "no_review_chat"
    assert not result.ok
    generate.assert_not_awaited()
    publish.assert_not_awaited()


async def test_generation_error_becomes_status_not_exception(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)

    with patch(
        "app.channel.generator.generate_post",
        new=AsyncMock(side_effect=RuntimeError("upstream exploded")),
    ):
        result = await _run(session_maker)

    assert result.status == "generation_failed"
    assert not result.ok


async def test_empty_generation_reported_separately(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)

    with patch("app.channel.generator.generate_post", new=AsyncMock(return_value=None)):
        result = await _run(session_maker)

    assert result.status == "generation_empty"


@pytest.mark.parametrize(
    ("send_mock", "case"),
    [
        (AsyncMock(return_value=None), "no post id"),
        (AsyncMock(side_effect=RuntimeError("telegram down")), "send raised"),
    ],
)
async def test_failed_review_send_reported(session_maker, send_mock, case) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock(return_value=_post())),
        patch("app.channel.review.send_for_review", new=send_mock),
    ):
        result = await _run(session_maker)

    assert result.status == "review_send_failed", case
    assert not result.ok


async def test_failed_direct_publish_reported(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=None)

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock(return_value=_post())),
        patch("app.channel.publisher.publish_post", new=AsyncMock(return_value=None)),
    ):
        result = await _run(session_maker)

    assert result.status == "publish_failed"


async def test_long_preview_is_truncated(session_maker) -> None:
    await _add_channel(session_maker, review_chat_id=-100500)
    long_text = "x" * (PREVIEW_CHARS + 50)

    with (
        patch("app.channel.generator.generate_post", new=AsyncMock(return_value=_post(long_text))),
        patch("app.channel.review.send_for_review", new=AsyncMock(return_value=1)),
    ):
        result = await _run(session_maker)

    assert result.preview == "x" * PREVIEW_CHARS + "..."
