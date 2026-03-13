"""Tests for review_service pure helper functions."""

from app.agent.channel.review.service import extract_source_btn_data, extract_source_urls


class _FakePost:
    def __init__(self, source_items):
        self.source_items = source_items


class TestExtractSourceBtnData:
    def test_none_source_items(self):
        assert extract_source_btn_data(_FakePost(None)) == []

    def test_empty_list(self):
        assert extract_source_btn_data(_FakePost([])) == []

    def test_caps_at_2_items(self):
        items = [{"title": f"Title {i}", "url": f"https://example.com/{i}"} for i in range(5)]
        result = extract_source_btn_data(_FakePost(items))
        assert len(result) <= 2

    def test_rejects_non_http_url(self):
        result = extract_source_btn_data(_FakePost([{"title": "Bad", "url": "ftp://example.com"}]))
        assert result == []

    def test_truncates_title_to_25_chars(self):
        result = extract_source_btn_data(_FakePost([{"title": "A" * 50, "url": "https://example.com"}]))
        assert len(result) == 1
        assert len(result[0]["title"]) <= 25

    def test_uses_source_url_fallback(self):
        result = extract_source_btn_data(_FakePost([{"title": "Test", "source_url": "https://example.com"}]))
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com"

    def test_missing_url_key(self):
        result = extract_source_btn_data(_FakePost([{"title": "No URL"}]))
        assert result == []

    def test_prefers_url_over_source_url(self):
        result = extract_source_btn_data(
            _FakePost([{"title": "T", "url": "https://a.com", "source_url": "https://b.com"}])
        )
        assert result[0]["url"] == "https://a.com"


class TestExtractSourceUrls:
    def test_none_source_items(self):
        assert extract_source_urls(_FakePost(None)) == []

    def test_empty_list(self):
        assert extract_source_urls(_FakePost([])) == []

    def test_deduplicates(self):
        items = [
            {"source_url": "https://example.com/1"},
            {"source_url": "https://example.com/1"},
            {"source_url": "https://example.com/2"},
        ]
        result = extract_source_urls(_FakePost(items))
        assert result == ["https://example.com/1", "https://example.com/2"]

    def test_skips_none_source_url(self):
        items = [{"title": "No URL"}, {"source_url": "https://example.com"}]
        result = extract_source_urls(_FakePost(items))
        assert result == ["https://example.com"]

    def test_preserves_order(self):
        items = [
            {"source_url": "https://b.com"},
            {"source_url": "https://a.com"},
        ]
        result = extract_source_urls(_FakePost(items))
        assert result == ["https://b.com", "https://a.com"]
