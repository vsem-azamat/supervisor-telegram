"""Regression tests for image-pipeline config fields."""

from app.channel.config import ChannelAgentSettings


def test_default_vision_model():
    s = ChannelAgentSettings()
    assert s.vision_model == "google/gemini-2.5-flash"


def test_default_phash_thresholds():
    s = ChannelAgentSettings()
    assert s.image_phash_lookback_posts == 30
    assert s.image_phash_threshold == 10


def test_vision_model_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_VISION_MODEL", "anthropic/claude-haiku-4-5")
    s = ChannelAgentSettings()
    assert s.vision_model == "anthropic/claude-haiku-4-5"


def test_phash_lookback_env_override(monkeypatch):
    monkeypatch.setenv("CHANNEL_IMAGE_PHASH_LOOKBACK_POSTS", "15")
    s = ChannelAgentSettings()
    assert s.image_phash_lookback_posts == 15
