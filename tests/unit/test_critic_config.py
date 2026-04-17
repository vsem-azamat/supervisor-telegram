"""Tests for critic-related settings on ChannelAgentSettings."""

from __future__ import annotations

from app.channel.config import ChannelAgentSettings


def test_critic_enabled_default_false():
    s = ChannelAgentSettings()
    assert s.critic_enabled is False


def test_critic_model_default_sonnet():
    s = ChannelAgentSettings()
    assert s.critic_model == "anthropic/claude-sonnet-4-6"


def test_critic_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_CRITIC_ENABLED", "true")
    monkeypatch.setenv("CHANNEL_CRITIC_MODEL", "openai/gpt-5.1")
    s = ChannelAgentSettings()
    assert s.critic_enabled is True
    assert s.critic_model == "openai/gpt-5.1"
