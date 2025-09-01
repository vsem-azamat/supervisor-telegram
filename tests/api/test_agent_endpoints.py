"""Tests for agent API endpoints."""

from unittest.mock import patch

import pytest
from app.presentation.api.routers.agent import router


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


class TestAgentEndpoints:
    """Test agent API endpoints structure."""

    def test_router_exists(self):
        """Test that agent router exists and has routes."""
        assert router is not None
        assert len(router.routes) > 0

    def test_router_has_required_endpoints(self):
        """Test that router has all required endpoint paths."""
        # Get all route paths
        route_paths = [route.path for route in router.routes if hasattr(route, "path")]

        # Check for required endpoints
        assert any("/models" in path for path in route_paths)
        assert any("/sessions" in path for path in route_paths)

    def test_router_has_correct_methods(self):
        """Test that router has endpoints with correct HTTP methods."""
        # Get all routes with methods
        route_methods = []
        for route in router.routes:
            if hasattr(route, "methods"):
                route_methods.extend(route.methods)

        # Should have GET and POST methods
        assert "GET" in route_methods
        assert "POST" in route_methods

    @patch("app.presentation.api.routers.agent.get_agent_service")
    @patch("app.presentation.api.routers.agent.get_current_admin_user")
    def test_list_available_models_function_exists(self, mock_auth, mock_service):
        """Test that list_available_models function can be imported."""
        from app.presentation.api.routers.agent import list_available_models

        # Function exists and can be imported
        assert callable(list_available_models)

    @patch("app.presentation.api.routers.agent.get_agent_service")
    @patch("app.presentation.api.routers.agent.get_current_admin_user")
    def test_create_session_function_exists(self, mock_auth, mock_service):
        """Test that create_session function can be imported."""
        from app.presentation.api.routers.agent import create_session

        # Function exists and can be imported
        assert callable(create_session)
