"""Tests for critic integration inside generate_post."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.generator import generate_post
from app.channel.sources import ContentItem

pytestmark = pytest.mark.asyncio


FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"
RAW_TEXT = f"🎓 **Headline**\n\nBody with [link](https://x/1) text.\n\n{FOOTER}"
POLISHED_TEXT = f"🎓 **Tighter Headline**\n\nBody with [link](https://x/1) text.\n\n{FOOTER}"


def _fake_generation_result(text: str):
    from types import SimpleNamespace

    from app.channel.generator import GeneratedPost

    return SimpleNamespace(output=GeneratedPost(text=text))


@pytest.fixture
def sample_items() -> list[ContentItem]:
    return [
        ContentItem(
            source_url="https://rss/x",
            external_id="abc",
            title="Headline",
            body="Body",
            url="https://x/1",
        )
    ]


async def test_generate_post_applies_critic_when_enabled(sample_items):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch(
            "app.channel.critic.polish_post",
            new=AsyncMock(return_value=POLISHED_TEXT),
        ),
    ):
        out = await generate_post(
            sample_items,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == POLISHED_TEXT
    assert out.pre_critic_text == RAW_TEXT


async def test_generate_post_no_critic_when_disabled(sample_items):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch("app.channel.critic.polish_post", new=AsyncMock()) as polish_mock,
    ):
        out = await generate_post(
            sample_items,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=False,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
    polish_mock.assert_not_awaited()


async def test_generate_post_no_critic_when_model_empty(sample_items):
    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch("app.channel.critic.polish_post", new=AsyncMock()) as polish_mock,
    ):
        out = await generate_post(
            sample_items,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
    polish_mock.assert_not_awaited()


async def test_generate_post_silent_fallback_on_critic_error(sample_items):
    from app.channel.critic import CriticError

    with (
        patch(
            "app.channel.generator._create_generation_agent",
            return_value=__import__("types").SimpleNamespace(
                run=AsyncMock(return_value=_fake_generation_result(RAW_TEXT))
            ),
        ),
        patch(
            "app.channel.generator.extract_usage_from_pydanticai_result",
            return_value=None,
        ),
        patch(
            "app.channel.critic.polish_post",
            new=AsyncMock(side_effect=CriticError("nope")),
        ),
    ):
        out = await generate_post(
            sample_items,
            api_key="k",
            model="m",
            footer=FOOTER,
            critic_enabled=True,
            critic_model="anthropic/claude-sonnet-4-6",
        )
    assert out is not None
    assert out.text == RAW_TEXT
    assert out.pre_critic_text is None
