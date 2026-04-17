"""Unit tests for _render_review_message: chooses the right mode based on image count."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.channel.review.telegram_io import _render_review_message

pytestmark = pytest.mark.asyncio


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="x")]])


async def test_render_text_mode_no_images():
    bot = SimpleNamespace()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=2001))
    bot.send_photo = AsyncMock()
    bot.send_media_group = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text="hello", image_urls=[], keyboard=_kb()
    )

    assert pult_id == 2001
    assert album_ids is None
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()


async def test_render_single_mode_one_image():
    bot = SimpleNamespace()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=2002))
    bot.send_media_group = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text="hello", image_urls=["https://x/a.jpg"], keyboard=_kb()
    )

    assert pult_id == 2002
    assert album_ids is None
    bot.send_photo.assert_awaited_once()
    # parse_mode must be None to preserve entities past the bot's default HTML mode
    kwargs = bot.send_photo.await_args.kwargs
    assert kwargs.get("parse_mode") is None
    bot.send_message.assert_not_awaited()
    bot.send_media_group.assert_not_awaited()


async def test_render_album_mode_two_or_more_images():
    bot = SimpleNamespace()
    album_msgs = [SimpleNamespace(message_id=3001), SimpleNamespace(message_id=3002)]
    bot.send_media_group = AsyncMock(return_value=album_msgs)
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=3003))
    bot.send_photo = AsyncMock()

    pult_id, album_ids = await _render_review_message(
        bot,
        chat_id=-100,
        post_text="hello",
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        keyboard=_kb(),
    )

    assert pult_id == 3003
    assert album_ids == [3001, 3002]
    bot.send_media_group.assert_awaited_once()
    # pult must reply to the first album photo so Telegram visually groups them
    pult_kwargs = bot.send_message.await_args.kwargs
    assert pult_kwargs.get("reply_to_message_id") == 3001
    assert pult_kwargs.get("parse_mode") is None
    bot.send_photo.assert_not_awaited()


async def test_render_single_mode_long_text_falls_back_to_text_message():
    """Existing behaviour: if caption > 1024 chars, image is dropped (text-only msg)."""
    bot = SimpleNamespace()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=4001))
    bot.send_photo = AsyncMock()
    bot.send_media_group = AsyncMock()

    long_text = "x" * 1100
    pult_id, album_ids = await _render_review_message(
        bot, chat_id=-100, post_text=long_text, image_urls=["https://x/a.jpg"], keyboard=_kb()
    )

    assert pult_id == 4001
    assert album_ids is None
    bot.send_message.assert_awaited_once()
    bot.send_photo.assert_not_awaited()
