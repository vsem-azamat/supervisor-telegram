"""Unit tests for channel publisher — all branching paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel, Field


class _FakePost(BaseModel):
    text: str = "Test post"
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)


def _make_bot(**overrides: object) -> MagicMock:
    bot = MagicMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message = AsyncMock(return_value=msg)
    bot.send_photo = AsyncMock(return_value=msg)
    bot.send_media_group = AsyncMock(return_value=[msg])
    for k, v in overrides.items():
        setattr(bot, k, v)
    return bot


class TestPublishPost:
    """Tests for the top-level publish_post routing."""

    async def test_text_only_no_images(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        post = _FakePost(text="Hello world")
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        bot.send_message.assert_awaited_once()
        bot.send_photo.assert_not_awaited()
        bot.send_media_group.assert_not_awaited()

    async def test_single_image_short_caption(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        post = _FakePost(text="Short caption", image_urls=["https://example.com/img.jpg"])
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        bot.send_photo.assert_awaited_once()
        call_kwargs = bot.send_photo.call_args
        assert call_kwargs.kwargs.get("caption") == "Short caption"

    async def test_single_image_long_caption(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        long_text = "A" * 1025
        post = _FakePost(text=long_text, image_urls=["https://example.com/img.jpg"])
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        # Should send photo first, then text as reply
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_awaited_once()

    async def test_multi_image_media_group(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        post = _FakePost(
            text="Album post",
            image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        bot.send_media_group.assert_awaited_once()

    async def test_multi_image_long_caption_sends_text_reply(self) -> None:
        from app.agent.channel.publisher import publish_post

        msg = MagicMock()
        msg.message_id = 42
        bot = _make_bot(send_media_group=AsyncMock(return_value=[msg]))
        long_text = "B" * 1025
        post = _FakePost(
            text=long_text,
            image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id is not None
        bot.send_media_group.assert_awaited_once()
        # Text should be sent as a reply to the media group
        bot.send_message.assert_awaited_once()

    async def test_media_group_failure_falls_back_to_photo(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot(send_media_group=AsyncMock(side_effect=Exception("Telegram error")))
        post = _FakePost(
            text="Fallback test",
            image_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        # Should have tried media_group, failed, then fell back to send_photo
        bot.send_media_group.assert_awaited_once()
        bot.send_photo.assert_awaited_once()

    async def test_photo_failure_falls_back_to_text(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot(
            send_photo=AsyncMock(side_effect=Exception("Photo error")),
        )
        post = _FakePost(text="Final fallback", image_urls=["https://example.com/1.jpg"])
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        bot.send_photo.assert_awaited_once()
        bot.send_message.assert_awaited_once()

    async def test_image_url_backward_compat(self) -> None:
        """image_url (singular) is used when image_urls is empty."""
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        post = _FakePost(text="Compat", image_url="https://example.com/old.jpg", image_urls=[])
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id == 42
        bot.send_photo.assert_awaited_once()

    async def test_returns_none_on_total_failure(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot(
            send_message=AsyncMock(side_effect=Exception("All failed")),
        )
        post = _FakePost(text="Doomed")
        msg_id = await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        assert msg_id is None

    async def test_media_group_respects_10_image_limit(self) -> None:
        from app.agent.channel.publisher import publish_post

        bot = _make_bot()
        post = _FakePost(
            text="Many images",
            image_urls=[f"https://example.com/{i}.jpg" for i in range(15)],
        )
        await publish_post(bot, "@test", post)  # type: ignore[arg-type]

        bot.send_media_group.assert_awaited_once()
        media_arg = bot.send_media_group.call_args.kwargs.get("media")
        assert media_arg is not None
        assert len(media_arg) <= 10
