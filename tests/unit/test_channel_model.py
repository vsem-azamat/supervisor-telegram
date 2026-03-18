"""Tests for Channel and ChannelPost ORM model properties and domain methods."""

from __future__ import annotations

from datetime import timedelta

from app.agent.channel.config import language_name
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.infrastructure.db.models import Channel, ChannelPost

# ---------------------------------------------------------------------------
# Channel.footer property
# ---------------------------------------------------------------------------


class TestChannelFooter:
    def test_footer_with_template(self) -> None:
        ch = Channel(telegram_id=-1001234567890, name="Test", footer_template="Custom footer")
        assert ch.footer == "Custom footer"

    def test_footer_without_template_uses_username(self) -> None:
        ch = Channel(telegram_id=-1001234567890, name="MyChannel", username="mychan")
        assert "MyChannel" in ch.footer
        assert "@mychan" in ch.footer

    def test_footer_without_username_uses_numeric_id(self) -> None:
        ch = Channel(telegram_id=-1001234567890, name="TestChan")
        assert "TestChan" in ch.footer
        assert "@" not in ch.footer

    def test_footer_numeric_id_no_at_mention(self) -> None:
        ch = Channel(telegram_id=-1001234567890, name="NumChannel")
        assert "NumChannel" in ch.footer
        assert "@" not in ch.footer

    def test_footer_username_with_at_prefix_no_double_at(self) -> None:
        """Regression: username stored with @ prefix must not produce @@username."""
        ch = Channel(telegram_id=-1001234567890, name="TestChan", username="@test_chan")
        assert "@@" not in ch.footer
        assert "@test_chan" in ch.footer


# ---------------------------------------------------------------------------
# ChannelPost domain methods (.schedule(), .confirm_published(), .unschedule())
# ---------------------------------------------------------------------------


class TestChannelPostScheduleMethods:
    def test_schedule(self) -> None:
        post = ChannelPost(channel_id=-1001234567890, external_id="e1", title="T", post_text="text")
        t = utc_now()
        post.schedule(t, 42)
        assert post.status == PostStatus.SCHEDULED
        assert post.scheduled_at == t
        assert post.scheduled_telegram_id == 42

    def test_confirm_published(self) -> None:
        post = ChannelPost(channel_id=-1001234567890, external_id="e1", title="T", post_text="text")
        post.schedule(utc_now(), 42)
        post.confirm_published(100)
        assert post.status == PostStatus.APPROVED
        assert post.telegram_message_id == 100
        assert post.published_at is not None

    def test_reschedule(self) -> None:
        post = ChannelPost(channel_id=-1001234567890, external_id="e1", title="T", post_text="text")
        t1 = utc_now()
        t2 = utc_now() + timedelta(hours=1)
        post.schedule(t1, 42)
        post.reschedule(t2, 99)
        assert post.scheduled_at == t2
        assert post.scheduled_telegram_id == 99

    def test_unschedule(self) -> None:
        post = ChannelPost(channel_id=-1001234567890, external_id="e1", title="T", post_text="text")
        post.schedule(utc_now(), 42)
        post.unschedule()
        assert post.status == PostStatus.DRAFT
        assert post.scheduled_at is None
        assert post.scheduled_telegram_id is None


# ---------------------------------------------------------------------------
# Channel.reset_daily_count() and language_name()
# ---------------------------------------------------------------------------


class TestChannelModel:
    def test_daily_count_reset(self):
        ch = Channel(
            telegram_id=-1001234567890,
            name="Test Channel",
            description="Test channel for unit tests",
            language="en",
            review_chat_id=-1009999999999,
            max_posts_per_day=3,
        )
        ch.daily_posts_count = 5
        ch.daily_count_date = "2020-01-01"
        ch.reset_daily_count("2020-01-02")
        assert ch.daily_posts_count == 0

    def test_daily_count_no_reset_same_day(self):
        ch = Channel(
            telegram_id=-1001234567890,
            name="Test Channel",
            description="Test channel for unit tests",
            language="en",
            review_chat_id=-1009999999999,
            max_posts_per_day=3,
        )
        ch.daily_posts_count = 2
        ch.daily_count_date = "2020-01-01"
        ch.reset_daily_count("2020-01-01")
        assert ch.daily_posts_count == 2

    def test_language_name(self):
        ch = Channel(
            telegram_id=-1001234567890,
            name="Test Channel",
            description="Test channel for unit tests",
            language="en",
            review_chat_id=-1009999999999,
            max_posts_per_day=3,
        )
        ch.language = "ru"
        assert language_name(ch.language) == "Russian"

        ch.language = "cs"
        assert language_name(ch.language) == "Czech"
