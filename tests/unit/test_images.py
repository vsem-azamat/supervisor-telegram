"""Unit tests for channel image extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.channel.images import (
    _has_small_width_hint,
    _is_valid_image_url,
    _normalize_image_url,
    extract_rss_media_url,
    find_image_for_post,
    find_images_for_post,
)

# ---------------------------------------------------------------------------
# _normalize_image_url
# ---------------------------------------------------------------------------


class TestNormalizeImageUrl:
    def test_protocol_relative(self) -> None:
        result = _normalize_image_url("//cdn.example.com/img.jpg", "https://page.com/article")
        assert result == "https://cdn.example.com/img.jpg"

    def test_relative_path(self) -> None:
        result = _normalize_image_url("/images/photo.jpg", "https://page.com/article")
        assert result == "https://page.com/images/photo.jpg"

    def test_absolute_https(self) -> None:
        url = "https://cdn.example.com/photo.jpg"
        result = _normalize_image_url(url, "https://page.com/article")
        assert result == url

    def test_absolute_http(self) -> None:
        url = "http://cdn.example.com/photo.jpg"
        result = _normalize_image_url(url, "https://page.com/article")
        assert result == url

    def test_data_uri_returns_none(self) -> None:
        result = _normalize_image_url("data:image/png;base64,abc", "https://page.com")
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        result = _normalize_image_url("", "https://page.com")
        assert result is None

    def test_bare_relative_returns_none(self) -> None:
        result = _normalize_image_url("images/foo.jpg", "https://page.com")
        assert result is None


# ---------------------------------------------------------------------------
# _is_valid_image_url
# ---------------------------------------------------------------------------


class TestIsValidImageUrl:
    def test_jpg_extension(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/photo.jpg")

    def test_png_extension(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/photo.png")

    def test_webp_extension(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/photo.webp")

    def test_gif_extension(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/animation.gif")

    def test_jpeg_extension(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/photo.jpeg")

    def test_image_keyword_in_path(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/media/story123")

    def test_upload_keyword(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/upload/123")

    def test_no_extension_no_keyword_rejected(self) -> None:
        assert not _is_valid_image_url("https://cdn.example.com/api/data")

    def test_query_params_stripped_for_extension_check(self) -> None:
        assert _is_valid_image_url("https://cdn.example.com/photo.jpg?width=800")


# ---------------------------------------------------------------------------
# _has_small_width_hint
# ---------------------------------------------------------------------------


class TestHasSmallWidthHint:
    def test_query_param_small(self) -> None:
        assert _has_small_width_hint("https://example.com/img?width=200")

    def test_query_param_large(self) -> None:
        assert not _has_small_width_hint("https://example.com/img?width=800")

    def test_path_segment_small(self) -> None:
        assert _has_small_width_hint("https://example.com/width/100/img.jpg")

    def test_no_width_returns_false(self) -> None:
        assert not _has_small_width_hint("https://example.com/img.jpg")

    def test_exact_boundary_400(self) -> None:
        assert not _has_small_width_hint("https://example.com/img?width=400")

    def test_just_below_boundary(self) -> None:
        assert _has_small_width_hint("https://example.com/img?width=399")


# ---------------------------------------------------------------------------
# extract_rss_media_url
# ---------------------------------------------------------------------------


class TestExtractRssMediaUrl:
    def test_media_content(self) -> None:
        entry = MagicMock()
        entry.media_content = [{"url": "https://example.com/media.jpg"}]
        entry.media_thumbnail = []
        entry.enclosures = []
        entry.links = []
        assert extract_rss_media_url(entry) == "https://example.com/media.jpg"

    def test_media_thumbnail(self) -> None:
        entry = MagicMock()
        entry.media_content = []
        entry.media_thumbnail = [{"url": "https://example.com/thumb.jpg"}]
        entry.enclosures = []
        entry.links = []
        assert extract_rss_media_url(entry) == "https://example.com/thumb.jpg"

    def test_enclosure_image(self) -> None:
        entry = MagicMock()
        entry.media_content = []
        entry.media_thumbnail = []
        entry.enclosures = [{"type": "image/jpeg", "href": "https://example.com/enc.jpg"}]
        entry.links = []
        assert extract_rss_media_url(entry) == "https://example.com/enc.jpg"

    def test_enclosure_image_with_url_key(self) -> None:
        """Enclosures with 'url' key instead of 'href' should also be extracted."""
        entry = MagicMock()
        entry.media_content = []
        entry.media_thumbnail = []
        entry.enclosures = [{"type": "image/png", "url": "https://example.com/enc_url.png"}]
        entry.links = []
        assert extract_rss_media_url(entry) == "https://example.com/enc_url.png"

    def test_link_image(self) -> None:
        entry = MagicMock()
        entry.media_content = []
        entry.media_thumbnail = []
        entry.enclosures = []
        entry.links = [{"type": "image/jpeg", "href": "https://example.com/link.jpg"}]
        assert extract_rss_media_url(entry) == "https://example.com/link.jpg"

    def test_no_media_returns_none(self) -> None:
        entry = MagicMock()
        entry.media_content = []
        entry.media_thumbnail = []
        entry.enclosures = []
        entry.links = []
        assert extract_rss_media_url(entry) is None

    def test_priority_media_content_over_thumbnail(self) -> None:
        entry = MagicMock()
        entry.media_content = [{"url": "https://example.com/full.jpg"}]
        entry.media_thumbnail = [{"url": "https://example.com/thumb.jpg"}]
        entry.enclosures = []
        entry.links = []
        assert extract_rss_media_url(entry) == "https://example.com/full.jpg"


# ---------------------------------------------------------------------------
# find_images_for_post
# ---------------------------------------------------------------------------


class TestFindImagesForPost:
    @pytest.fixture
    def _mock_http(self):
        """Shared patch context for HTTP client and SSRF check."""
        self._mock_client = AsyncMock()
        with (
            patch("app.channel.images.get_http_client", return_value=self._mock_client),
            patch("app.channel.images.is_safe_url", new=AsyncMock(return_value=True)),
        ):
            yield

    async def test_empty_urls_returns_empty(self) -> None:
        result = await find_images_for_post(keywords="test", source_urls=[])
        assert result == []

    async def test_none_urls_returns_empty(self) -> None:
        result = await find_images_for_post(keywords="test", source_urls=None)
        assert result == []

    @pytest.mark.usefixtures("_mock_http")
    async def test_http_error_returns_empty(self) -> None:
        self._mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        result = await find_images_for_post(keywords="test", source_urls=["https://example.com/article"])
        assert result == []

    @pytest.mark.usefixtures("_mock_http")
    async def test_og_image_extracted(self) -> None:
        html = '<html><head><meta property="og:image" content="https://cdn.example.com/og.jpg"></head></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        self._mock_client.get = AsyncMock(return_value=mock_resp)

        result = await find_images_for_post(keywords="test", source_urls=["https://example.com/article"])
        assert len(result) == 1
        assert result[0] == "https://cdn.example.com/og.jpg"

    @pytest.mark.usefixtures("_mock_http")
    async def test_respects_max_images(self) -> None:
        html = """<html><head>
            <meta property="og:image" content="https://cdn.example.com/1.jpg">
        </head><body>
            <img src="https://cdn.example.com/2.jpg" width="800">
            <img src="https://cdn.example.com/3.jpg" width="800">
            <img src="https://cdn.example.com/4.jpg" width="800">
            <img src="https://cdn.example.com/5.jpg" width="800">
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        self._mock_client.get = AsyncMock(return_value=mock_resp)

        result = await find_images_for_post(
            keywords="test",
            source_urls=["https://example.com/article"],
            max_images=2,
        )
        assert len(result) <= 2


class TestFindImageForPost:
    async def test_backward_compat_returns_single(self) -> None:
        with patch(
            "app.channel.images.find_images_for_post",
            new=AsyncMock(return_value=["https://example.com/img.jpg"]),
        ):
            result = await find_image_for_post(keywords="test", source_urls=["https://example.com"])
            assert result == "https://example.com/img.jpg"

    async def test_backward_compat_returns_none_when_empty(self) -> None:
        with patch(
            "app.channel.images.find_images_for_post",
            new=AsyncMock(return_value=[]),
        ):
            result = await find_image_for_post(keywords="test", source_urls=["https://example.com"])
            assert result is None
