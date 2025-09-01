"""Tests for API key manager."""

import os

from app.application.services.api_key_manager import with_api_key


class TestAPIKeyManager:
    """Test API key manager context manager."""

    def test_with_api_key_basic_usage(self):
        """Test basic API key context manager usage."""
        test_key = "sk-test-key-123"
        original_key = os.environ.get("OPENAI_API_KEY")

        # Test that key is set within context
        with with_api_key(test_key):
            assert os.environ.get("OPENAI_API_KEY") == test_key

        # Test that original key is restored
        assert os.environ.get("OPENAI_API_KEY") == original_key

    def test_with_api_key_with_base_url(self):
        """Test API key manager with base URL."""
        test_key = "sk-test-key-123"
        test_base_url = "https://test.api.com"
        original_key = os.environ.get("OPENAI_API_KEY")
        original_base_url = os.environ.get("OPENAI_BASE_URL")

        with with_api_key(test_key, test_base_url):
            assert os.environ.get("OPENAI_API_KEY") == test_key
            assert os.environ.get("OPENAI_BASE_URL") == test_base_url

        # Test that originals are restored
        assert os.environ.get("OPENAI_API_KEY") == original_key
        assert os.environ.get("OPENAI_BASE_URL") == original_base_url

    def test_with_api_key_exception_handling(self):
        """Test that original values are restored even if exception occurs."""
        test_key = "sk-test-key-123"
        original_key = os.environ.get("OPENAI_API_KEY")

        try:
            with with_api_key(test_key):
                assert os.environ.get("OPENAI_API_KEY") == test_key
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Original key should still be restored
        assert os.environ.get("OPENAI_API_KEY") == original_key

    def test_with_api_key_no_original_key(self):
        """Test behavior when no original key exists."""
        test_key = "sk-test-key-123"

        # Ensure no original key
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

        with with_api_key(test_key):
            assert os.environ.get("OPENAI_API_KEY") == test_key

        # Should be removed after context
        assert "OPENAI_API_KEY" not in os.environ

    def test_with_api_key_preserves_existing_key(self):
        """Test that existing key is properly preserved and restored."""
        original_key = "sk-original-key"
        test_key = "sk-test-key-123"

        # Set original key
        os.environ["OPENAI_API_KEY"] = original_key

        try:
            with with_api_key(test_key):
                assert os.environ.get("OPENAI_API_KEY") == test_key

            # Should restore original
            assert os.environ.get("OPENAI_API_KEY") == original_key
        finally:
            # Clean up
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
