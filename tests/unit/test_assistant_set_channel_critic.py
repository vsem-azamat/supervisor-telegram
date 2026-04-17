"""Tests for the set_channel_critic assistant tool."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.db.models import Channel
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class _Recorder:
    """Capture PydanticAI `@agent.tool` registrations so tests can call them."""

    def __init__(self):
        self.tools: dict = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


async def test_set_channel_critic_enables(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-123, name="X")
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-123, enabled=True)
    assert "True" in msg or "включ" in msg.lower()

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -123))).scalar_one()
    assert row.critic_enabled is True


async def test_set_channel_critic_disables(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-124, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    await tool(ctx, telegram_id=-124, enabled=False)

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -124))).scalar_one()
    assert row.critic_enabled is False


async def test_set_channel_critic_resets_to_global(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    async with session_maker() as session:
        ch = Channel(telegram_id=-125, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-125, enabled=None)
    assert "global" in msg.lower() or "глобал" in msg.lower()

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.telegram_id == -125))).scalar_one()
    assert row.critic_enabled is None


async def test_set_channel_critic_unknown_channel(session_maker):
    from app.assistant.tools.channel.channels import register_channels_tools

    recorder = _Recorder()
    register_channels_tools(recorder)  # type: ignore[arg-type]
    tool = recorder.tools["set_channel_critic"]

    ctx = SimpleNamespace(deps=SimpleNamespace(session_maker=session_maker))
    msg = await tool(ctx, telegram_id=-9999, enabled=True)
    assert "не найден" in msg.lower() or "not found" in msg.lower()
