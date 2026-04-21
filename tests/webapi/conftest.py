"""Shared fixtures for webapi tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def override_super_admins() -> Iterator[None]:
    """Context manager style: set settings.admin.super_admins for the test
    and restore afterwards. Used by tests that exercise the auth dep."""
    original = list(settings.admin.super_admins)
    yield
    settings.admin.super_admins = original
