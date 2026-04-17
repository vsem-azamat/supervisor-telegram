"""Tests for polish_post — happy path, retry, and CriticError on persistent failure."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.channel.critic import CriticError, polish_post

pytestmark = pytest.mark.asyncio

FOOTER = "——\n🔗 **Konnekt** | @konnekt_channel"

ORIGINAL = (
    "🎓 **Продлили дедлайн стипендии**\n\n"
    "ČVUT продлил приём заявок на [стипендию](https://cvut.cz/s) "
    "до 15 мая. Подать документы можно в деканате.\n\n" + FOOTER
)

POLISHED_OK = (
    "🎓 **Дедлайн стипендии ČVUT перенесли**\n\n"
    "ČVUT принимает заявки на [стипендию](https://cvut.cz/s) до 15 мая. "
    "Документы — в деканате.\n\n" + FOOTER
)

POLISHED_MISSING_FOOTER = (
    "🎓 **Дедлайн стипендии ČVUT перенесли**\n\nČVUT принимает заявки на [стипендию](https://cvut.cz/s) до 15 мая."
)


def _fake_run_result(output: str):
    """Build an object shaped like a PydanticAI RunResult for our purposes."""
    return SimpleNamespace(output=output)


async def test_polish_post_success():
    fake_agent = SimpleNamespace(run=AsyncMock(return_value=_fake_run_result(POLISHED_OK)))
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        out = await polish_post(text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6")
    assert out == POLISHED_OK
    assert fake_agent.run.await_count == 1


async def test_polish_post_retry_then_success():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),  # first call — violates footer
                _fake_run_result(POLISHED_OK),  # retry — ok
            ]
        )
    )
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        out = await polish_post(text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6")
    assert out == POLISHED_OK
    assert fake_agent.run.await_count == 2


async def test_polish_post_fails_after_retry():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),
                _fake_run_result(POLISHED_MISSING_FOOTER),
            ]
        )
    )
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        with pytest.raises(CriticError) as exc_info:
            await polish_post(text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6")
    assert "footer" in str(exc_info.value).lower()
    assert fake_agent.run.await_count == 2


async def test_polish_post_raises_on_llm_exception():
    fake_agent = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("openrouter 500")))
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", return_value=None),
    ):
        with pytest.raises(CriticError):
            await polish_post(text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6")


async def test_polish_post_logs_usage_per_call():
    fake_agent = SimpleNamespace(
        run=AsyncMock(
            side_effect=[
                _fake_run_result(POLISHED_MISSING_FOOTER),
                _fake_run_result(POLISHED_OK),
            ]
        )
    )
    # extract_usage_from_pydanticai_result is SYNC — use regular Mock, not AsyncMock.
    # Using AsyncMock would return a coroutine (truthy), which would be passed to
    # log_usage as `usage`, causing await log_usage(coroutine) to fail.
    extract_mock = Mock(return_value=None)
    log_mock = AsyncMock()
    with (
        patch("app.channel.critic._create_critic_agent", return_value=fake_agent),
        patch("app.channel.critic.extract_usage_from_pydanticai_result", side_effect=extract_mock),
        patch("app.channel.critic.log_usage", log_mock),
    ):
        await polish_post(text=ORIGINAL, footer=FOOTER, api_key="k", model="anthropic/claude-sonnet-4-6")

    # Two calls → two extract attempts, one per operation value.
    operations = [call.args[2] for call in extract_mock.call_args_list]
    assert operations == ["critic", "critic_retry"]
