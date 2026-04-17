"""Smoke test: FakeTelegramServer handles sendMediaGroup and deleteMessages."""

from __future__ import annotations

import json

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import InputMediaPhoto

from tests.fake_telegram import FakeTelegramServer

pytestmark = pytest.mark.asyncio


async def test_send_media_group_returns_distinct_message_ids():
    async with FakeTelegramServer() as server:
        bot = Bot(
            token="123:fake",
            session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
        )
        try:
            media = [
                InputMediaPhoto(media="https://example.com/a.jpg"),
                InputMediaPhoto(media="https://example.com/b.jpg"),
            ]
            messages = await bot.send_media_group(chat_id=-100, media=media)
        finally:
            await bot.session.close()

        assert len(messages) == 2
        assert messages[0].message_id != messages[1].message_id

        calls = server.get_calls("sendMediaGroup")
        assert len(calls) == 1
        media_param = calls[0].params.get("media")
        # aiogram serialises media as JSON string in multipart form
        parsed = json.loads(media_param) if isinstance(media_param, str) else media_param
        assert len(parsed) == 2


async def test_delete_messages_records_ids():
    async with FakeTelegramServer() as server:
        bot = Bot(
            token="123:fake",
            session=AiohttpSession(api=TelegramAPIServer.from_base(server.base_url)),
        )
        try:
            ok = await bot.delete_messages(chat_id=-100, message_ids=[1001, 1002, 1003])
        finally:
            await bot.session.close()

        assert ok is True
        calls = server.get_calls("deleteMessages")
        assert len(calls) == 1
        ids_param = calls[0].params.get("message_ids")
        parsed = json.loads(ids_param) if isinstance(ids_param, str) else ids_param
        assert list(parsed) == [1001, 1002, 1003]
