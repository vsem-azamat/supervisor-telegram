"""Full review-flow smoke test: album send → approve chain via FakeTelegramServer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import URLInputFile
from app.channel.generator import GeneratedPost
from app.channel.review.telegram_io import handle_delete, send_for_review
from app.db.models import ChannelPost
from sqlalchemy import select

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from tests.fake_telegram import FakeTelegramServer

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _stub_urlinputfile_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """URLInputFile normally streams bytes from the URL; in tests the URLs are
    unreachable (https://x/...), so we stub the read iterator with fake bytes so
    aiogram can build the multipart body and reach FakeTelegramServer."""

    async def _fake_read(self: URLInputFile, bot: Bot) -> AsyncGenerator[bytes, None]:
        yield b"fake-image-bytes"

    monkeypatch.setattr(URLInputFile, "read", _fake_read)


class _Item:
    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url
        self.body = "b"
        self.source_url = url
        self.external_id = url
        self.summary = "s"


async def _make_bot(server: FakeTelegramServer) -> Bot:
    return Bot(
        token="123:fake",
        session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
    )


async def test_send_album_for_review_produces_media_group_plus_pult(session_maker, fake_tg):
    bot = await _make_bot(fake_tg)
    try:
        post = GeneratedPost(
            text="Body text\n\n——\n🔗 **Konnekt**",
            image_url="https://x/a.jpg",
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        )
        post_id = await send_for_review(
            bot,
            review_chat_id=-100,
            channel_id=-100,
            post=post,
            source_items=[_Item("News", "https://src/1")],  # ty: ignore[invalid-argument-type]
            session_maker=session_maker,
        )
        assert post_id is not None
    finally:
        await bot.session.close()

    mg_calls = fake_tg.get_calls("sendMediaGroup")
    msg_calls = fake_tg.get_calls("sendMessage")
    assert len(mg_calls) == 1
    assert len(msg_calls) == 1

    mg_params = mg_calls[0].params
    media_raw = mg_params.get("media", "[]")
    media = json.loads(media_raw) if isinstance(media_raw, str) else media_raw
    assert len(media) == 2

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_album_message_ids is not None
        assert len(row.review_album_message_ids) == 2
        assert row.review_message_id


async def test_delete_album_post_issues_bulk_delete(session_maker, fake_tg):
    bot = await _make_bot(fake_tg)
    try:
        post = GeneratedPost(
            text="Body\n\n——\n🔗 **Konnekt**",
            image_url="https://x/a.jpg",
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
        )
        post_id = await send_for_review(
            bot,
            review_chat_id=-100,
            channel_id=-100,
            post=post,
            source_items=[_Item("News", "https://src/1")],  # ty: ignore[invalid-argument-type]
            session_maker=session_maker,
        )
        assert post_id is not None

        async with session_maker() as s:
            row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            pult = row.review_message_id

        fake_tg.reset()  # only observe the delete-path calls below

        await handle_delete(bot, post_id, -100, pult, session_maker)
    finally:
        await bot.session.close()

    # One bulk delete for the 2 album photos, plus one single delete for the pult.
    assert len(fake_tg.get_calls("deleteMessages")) == 1
    assert len(fake_tg.get_calls("deleteMessage")) == 1
