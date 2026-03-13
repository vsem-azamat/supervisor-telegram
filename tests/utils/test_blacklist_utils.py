"""Tests for blacklist utilities."""

import pytest
from app.infrastructure.db.models import User
from app.presentation.telegram.utils.blacklist import (
    build_blacklist_keyboard,
    build_blacklist_text,
    build_user_details_keyboard,
    build_user_details_text,
)


class TestBlacklistUtils:
    """Test cases for blacklist utility functions."""

    @pytest.fixture
    def sample_users(self):
        """Create sample users for testing."""
        return [
            User(id=123, username="testuser", first_name="Test", last_name="User", blocked=True),
            User(id=456, username="spammer", first_name="Spam", blocked=True),
            User(id=789, username=None, first_name=None, last_name=None, blocked=True),
        ]

    def test_build_blacklist_text_with_pagination(self, sample_users):
        """Test building blacklist text with pagination info."""
        text = build_blacklist_text(total_count=15, current_page=0, total_pages=2, page_size=10)

        assert "Blacklist (15 users)" in text
        assert "Showing 1-10 of 15" in text
        assert "Page 1 of 2" in text

    def test_build_blacklist_text_single_page(self, sample_users):
        """Test building blacklist text for single page."""
        text = build_blacklist_text(total_count=5, current_page=0, total_pages=1, page_size=10)

        assert "Blacklist (5 users)" in text
        assert "Showing" not in text
        assert "Page" not in text

    def test_build_blacklist_keyboard_single_page(self, sample_users):
        """Test building keyboard for single page."""
        keyboard = build_blacklist_keyboard(users=sample_users, current_page=0, total_pages=1, page_size=10)

        buttons = keyboard.as_markup().inline_keyboard
        # Should have 3 user buttons (one row each)
        assert len(buttons) == 3
        assert "Test User" in buttons[0][0].text
        assert "Spam" in buttons[1][0].text
        assert "User 789" in buttons[2][0].text

    def test_build_blacklist_keyboard_with_pagination(self, sample_users):
        """Test building keyboard with pagination controls."""
        # Create more users to test pagination
        many_users = sample_users * 5  # 15 users total

        keyboard = build_blacklist_keyboard(
            users=many_users,
            current_page=1,  # Second page (last page)
            total_pages=2,
            page_size=10,
        )

        buttons = keyboard.as_markup().inline_keyboard
        # Should have user buttons + pagination row
        assert len(buttons) > 5  # At least some user buttons

        # Check pagination row (last row) - should only have Prev and Page indicator for last page
        pagination_row = buttons[-1]
        assert len(pagination_row) == 2  # Prev, Page indicator (no Next for last page)
        assert "\u25c0\ufe0f Prev" in pagination_row[0].text
        assert "2/2" in pagination_row[1].text

    def test_build_blacklist_keyboard_first_page_pagination(self, sample_users):
        """Test building keyboard for first page with Next button."""
        # Create more users to test pagination
        many_users = sample_users * 5  # 15 users total

        keyboard = build_blacklist_keyboard(
            users=many_users,
            current_page=0,  # First page
            total_pages=2,
            page_size=10,
        )

        buttons = keyboard.as_markup().inline_keyboard
        # Check pagination row (last row) - should have Page indicator and Next for first page
        pagination_row = buttons[-1]
        assert len(pagination_row) == 2  # Page indicator, Next (no Prev for first page)
        assert "1/2" in pagination_row[0].text
        assert "Next \u25b6\ufe0f" in pagination_row[1].text

    def test_build_blacklist_keyboard_middle_page_pagination(self, sample_users):
        """Test building keyboard for middle page with both Prev and Next buttons."""
        many_users = sample_users * 5  # 15 users total

        keyboard = build_blacklist_keyboard(
            users=many_users,
            current_page=1,  # Middle page (page 2 of 3)
            total_pages=3,
            page_size=5,
        )

        buttons = keyboard.as_markup().inline_keyboard
        # Check pagination row (last row) - should have Prev, Page indicator, and Next
        pagination_row = buttons[-1]
        assert len(pagination_row) == 3  # Prev, Page indicator, Next
        assert "\u25c0\ufe0f Prev" in pagination_row[0].text
        assert "2/3" in pagination_row[1].text
        assert "Next \u25b6\ufe0f" in pagination_row[2].text

    def test_build_user_details_text(self, sample_users):
        """Test building user details text."""
        user = sample_users[0]  # Test User
        text = build_user_details_text(user)

        assert "Found in blacklist" in text
        assert "Test User" in text
        assert "123" in text
        assert "@testuser" in text

    def test_build_user_details_text_no_username(self, sample_users):
        """Test building user details text for user without username."""
        user = sample_users[2]  # User without username
        text = build_user_details_text(user)

        assert "Found in blacklist" in text
        assert "User 789" in text
        assert "789" in text
        assert "@" not in text  # No username section

    def test_build_user_details_keyboard(self, sample_users):
        """Test building user details keyboard."""
        user = sample_users[0]
        keyboard = build_user_details_keyboard(user)

        buttons = keyboard.as_markup().inline_keyboard
        assert len(buttons) == 1
        assert "Unblock User" in buttons[0][0].text

    def test_long_display_name_truncation(self):
        """Test that long display names are properly truncated."""
        user = User(
            id=999,
            username="verylongusernamethatexceedslimit",
            first_name="Very Long First Name That Exceeds Limit",
            last_name="Very Long Last Name",
            blocked=True,
        )

        keyboard = build_blacklist_keyboard(users=[user], current_page=0, total_pages=1, page_size=10)

        button_text = keyboard.as_markup().inline_keyboard[0][0].text
        # Should be truncated with ellipsis
        assert len(button_text) <= 33  # "🚫 " + 27 chars + "..."
        assert button_text.endswith("...")
