"""Tests for spam detection service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.application.services.spam import detect_spam


class TestDetectSpam:
    @pytest.fixture
    def db(self):
        return AsyncMock()

    def _make_message(self, *, text="Hello", from_user_id=123, chat_id=456):
        msg = MagicMock()
        msg.text = text
        msg.caption = None
        msg.chat.id = chat_id
        if from_user_id is not None:
            msg.from_user = MagicMock()
            msg.from_user.id = from_user_id
        else:
            msg.from_user = None
        return msg

    async def test_no_text_returns_false(self, db):
        msg = self._make_message(text=None)
        msg.caption = None
        assert await detect_spam(db, msg) is False

    async def test_no_from_user_returns_false(self, db):
        msg = self._make_message(from_user_id=None)
        assert await detect_spam(db, msg) is False

    async def test_user_with_previous_messages_returns_false(self, db):
        msg = self._make_message()
        mock_repo = MagicMock()
        mock_repo.has_previous_messages = AsyncMock(return_value=True)
        with patch("app.application.services.spam.get_message_repository", return_value=mock_repo):
            assert await detect_spam(db, msg) is False

    async def test_first_message_spam_returns_true(self, db):
        msg = self._make_message(text="Buy crypto now!")
        mock_repo = MagicMock()
        mock_repo.has_previous_messages = AsyncMock(return_value=False)
        mock_repo.is_similar_spam_message = AsyncMock(return_value=True)
        with patch("app.application.services.spam.get_message_repository", return_value=mock_repo):
            assert await detect_spam(db, msg) is True

    async def test_first_message_clean_returns_false(self, db):
        msg = self._make_message(text="Hello everyone!")
        mock_repo = MagicMock()
        mock_repo.has_previous_messages = AsyncMock(return_value=False)
        mock_repo.is_similar_spam_message = AsyncMock(return_value=False)
        with patch("app.application.services.spam.get_message_repository", return_value=mock_repo):
            assert await detect_spam(db, msg) is False

    async def test_caption_fallback(self, db):
        msg = self._make_message(text=None)
        msg.caption = "Buy crypto now!"
        mock_repo = MagicMock()
        mock_repo.has_previous_messages = AsyncMock(return_value=False)
        mock_repo.is_similar_spam_message = AsyncMock(return_value=True)
        with patch("app.application.services.spam.get_message_repository", return_value=mock_repo):
            result = await detect_spam(db, msg)
            # Caption should be used when text is None, and spam detection should proceed
            mock_repo.is_similar_spam_message.assert_awaited_once_with("Buy crypto now!")
            assert result is True
