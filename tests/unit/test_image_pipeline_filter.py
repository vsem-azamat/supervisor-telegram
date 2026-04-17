"""Unit tests for ``cheap_filter``."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.image_pipeline.filter import FilteredImage, cheap_filter

from tests.fixtures.images import make_test_image

pytestmark = pytest.mark.asyncio


def _response(data: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=data, request=httpx.Request("GET", "https://x"))


class TestCheapFilter:
    async def test_happy_path_large_colorful(self):
        data = make_test_image(width=1200, height=800, colors=300)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/ok.jpg"])
        assert len(result) == 1
        assert isinstance(result[0], FilteredImage)
        assert result[0].url == "https://x/ok.jpg"
        assert result[0].width == 1200
        assert result[0].height == 800
        assert result[0].bytes_ == data

    async def test_drops_small_image(self):
        data = make_test_image(width=400, height=300, colors=200)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/small.jpg"])
        assert result == []

    async def test_drops_extreme_aspect_ratio(self):
        data = make_test_image(width=2400, height=300, colors=200)  # 8:1
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/banner.jpg"])
        assert result == []

    async def test_drops_solid_color_low_entropy(self):
        data = make_test_image(width=1000, height=800, fill=(40, 40, 40), colors=None)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(data))):
            result = await cheap_filter(["https://x/logo.png"])
        assert result == []

    async def test_drops_oversize_bytes(self):
        """Anything over 20 MB → skipped without opening PIL."""
        huge = b"\x00" * (21 * 1024 * 1024)
        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(return_value=_response(huge))):
            result = await cheap_filter(["https://x/huge.bin"])
        assert result == []

    async def test_skips_download_failure_continues(self):
        """If one URL fails, others still processed."""
        good = make_test_image(width=900, height=700, colors=200)

        async def side_effect(url, **kwargs):
            if "bad" in url:
                raise httpx.ConnectError("boom")
            return _response(good)

        with patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=side_effect)):
            result = await cheap_filter(["https://x/bad.jpg", "https://x/ok.jpg"])
        assert len(result) == 1
        assert result[0].url == "https://x/ok.jpg"
