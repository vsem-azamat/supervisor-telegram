"""Tests for app.core.markdown — md_to_entities and md_to_entities_chunked."""

from __future__ import annotations

from app.core.markdown import md_to_entities, md_to_entities_chunked

# ---------------------------------------------------------------------------
# md_to_entities
# ---------------------------------------------------------------------------


class TestMdToEntities:
    def test_bold(self) -> None:
        text, entities = md_to_entities("**text**")
        assert text == "text"
        assert len(entities) == 1
        assert entities[0].type == "bold"

    def test_italic(self) -> None:
        text, entities = md_to_entities("*text*")
        assert text == "text"
        assert len(entities) == 1
        assert entities[0].type == "italic"

    def test_inline_code(self) -> None:
        text, entities = md_to_entities("`code`")
        assert text == "code"
        assert len(entities) == 1
        assert entities[0].type == "code"

    def test_code_block(self) -> None:
        text, entities = md_to_entities("```python\nprint(1)\n```")
        assert "print(1)" in text
        assert any(e.type == "pre" for e in entities)

    def test_link(self) -> None:
        text, entities = md_to_entities("[click](https://example.com)")
        assert text == "click"
        assert len(entities) == 1
        assert entities[0].type == "text_link"
        assert entities[0].url == "https://example.com"

    def test_mixed_formatting(self) -> None:
        text, entities = md_to_entities("**bold** and *italic* and `code`")
        assert "bold" in text
        assert "italic" in text
        assert "code" in text
        types = {e.type for e in entities}
        assert "bold" in types
        assert "italic" in types
        assert "code" in types

    def test_plain_text_no_entities(self) -> None:
        text, entities = md_to_entities("Hello, this is plain text.")
        assert text == "Hello, this is plain text."
        assert entities == []

    def test_html_chars_safe(self) -> None:
        text, entities = md_to_entities("I <3 cats & dogs")
        assert "<3" in text  # Literal, not HTML
        assert "&" in text  # Literal, not &amp;

    def test_channel_post_format(self) -> None:
        md = "💰 **Реальные зарплаты растут**\n\nТекст поста.\n\n[Подробнее](https://example.com)"
        text, entities = md_to_entities(md)
        assert "Реальные зарплаты растут" in text
        assert "Подробнее" in text
        assert any(e.type == "bold" for e in entities)
        assert any(e.type == "text_link" for e in entities)


# ---------------------------------------------------------------------------
# md_to_entities_chunked
# ---------------------------------------------------------------------------


class TestMdToEntitiesChunked:
    def test_short_text_single_chunk(self) -> None:
        chunks = md_to_entities_chunked("Hello **world**")
        assert len(chunks) == 1
        text, entities = chunks[0]
        assert "world" in text
        assert any(e.type == "bold" for e in entities)

    def test_empty_text(self) -> None:
        chunks = md_to_entities_chunked("")
        assert len(chunks) == 1
        assert chunks[0][0] == ""

    def test_respects_max_len(self) -> None:
        # Generate text longer than max_len
        long_md = "\n\n".join(f"Line {i}: " + "x" * 80 for i in range(100))
        chunks = md_to_entities_chunked(long_md, max_len=500)
        assert len(chunks) > 1
        for text, _ in chunks:
            assert len(text) <= 500


# ---------------------------------------------------------------------------
# md_to_entities_chunked boundary tests
# ---------------------------------------------------------------------------


class TestMdToEntitiesChunkedBoundary:
    def test_exactly_at_max_len_is_single_chunk(self) -> None:
        text = "a" * 4096
        chunks = md_to_entities_chunked(text)
        assert len(chunks) == 1
        assert len(chunks[0][0]) <= 4096

    def test_one_over_max_len_splits(self) -> None:
        text = "a" * 4097
        chunks = md_to_entities_chunked(text)
        assert len(chunks) >= 2
        for chunk_text, _ in chunks:
            assert len(chunk_text) <= 4096

    def test_custom_max_len_respected(self) -> None:
        text = "word " * 100  # 500 chars
        chunks = md_to_entities_chunked(text, max_len=100)
        assert len(chunks) >= 5
        for chunk_text, _ in chunks:
            assert len(chunk_text) <= 100
