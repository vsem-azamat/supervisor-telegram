"""Tests for chat API endpoints."""

from unittest.mock import patch

import pytest
from app.presentation.api.main import app
from app.presentation.api.routers.chats import router
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user."""
    return {
        "id": 123456789,
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "is_super_admin": True,
        "telegram_data": {},
    }


class TestChatEndpoints:
    """Test chat API endpoints."""

    async def test_health_check(self):
        """Test health check endpoint."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "message": "API is running"}

    def test_chat_router_exists(self):
        """Test that chat router exists and has routes."""
        assert router is not None
        assert len(router.routes) > 0

    def test_chat_router_has_required_endpoints(self):
        """Test that router has all required endpoint paths."""
        # Get all route paths
        route_paths = [route.path for route in router.routes if hasattr(route, "path")]

        # Check for required endpoints
        assert "" in route_paths  # GET /chats/
        assert "/{chat_id}" in route_paths  # GET /chats/{chat_id}
        assert "/bulk-update" in route_paths  # POST /chats/bulk-update

    @patch("app.presentation.api.routers.chats.get_chat_repository")
    @patch("app.presentation.api.routers.chats.get_current_admin_user")
    def test_get_all_chats_function_exists(self, mock_auth, mock_repo):
        """Test that get_all_chats function can be imported."""
        from app.presentation.api.routers.chats import get_all_chats

        # Function exists and can be imported
        assert callable(get_all_chats)

    @patch("app.presentation.api.routers.chats.get_chat_repository")
    def test_get_chat_function_exists(self, mock_repo):
        """Test that get_chat function can be imported."""
        from app.presentation.api.routers.chats import get_chat

        # Function exists and can be imported
        assert callable(get_chat)
