"""Unit tests for channel generator — sanitization, screening, generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.channel.generator import _sanitize_content, generate_post, screen_items

# ---------------------------------------------------------------------------
# _sanitize_content
# ---------------------------------------------------------------------------


class TestSanitizeContent:
    def test_strips_html_tags(self) -> None:
        assert _sanitize_content("<b>Hello</b> world") == "Hello world"

    def test_strips_nested_tags(self) -> None:
        assert _sanitize_content('<a href="x"><b>text</b></a>') == "text"

    def test_empty_string(self) -> None:
        assert _sanitize_content("") == ""

    def test_no_tags_unchanged(self) -> None:
        assert _sanitize_content("plain text 123") == "plain text 123"

    def test_strips_self_closing_tags(self) -> None:
        assert _sanitize_content("before<br/>after") == "beforeafter"

    def test_strips_script_tags(self) -> None:
        result = _sanitize_content("<script>alert('xss')</script>")
        assert "script" not in result
        assert "alert" in result  # content between tags is kept

    def test_greedy_strips_angle_bracket_content(self) -> None:
        # The regex is intentionally greedy for security — anything between < > is stripped
        assert _sanitize_content("a < b > c") == "a  c"


# ---------------------------------------------------------------------------
# screen_items — batch path (openrouter_chat_completion)
# ---------------------------------------------------------------------------


class TestScreenItems:
    async def test_empty_list_returns_empty(self) -> None:
        result = await screen_items([], api_key="k", model="m")
        assert result == []

    async def test_batch_filters_by_threshold(self) -> None:
        """Primary path: openrouter_chat_completion returns JSON scores."""
        items = [MagicMock(title="Good", summary="relevant content", external_id="1")]

        with patch(
            "app.channel.llm_client.openrouter_chat_completion",
            new_callable=AsyncMock,
            return_value=json.dumps({"0": 8}),
        ):
            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            assert len(result) == 1
            assert result[0].title == "Good"

    async def test_batch_below_threshold_filtered_out(self) -> None:
        """Primary path: items scoring below threshold are excluded."""
        items = [MagicMock(title="Bad", summary="irrelevant", external_id="1")]

        with patch(
            "app.channel.llm_client.openrouter_chat_completion",
            new_callable=AsyncMock,
            return_value=json.dumps({"0": 2}),
        ):
            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            assert len(result) == 0

    async def test_batch_multiple_items_mixed_scores(self) -> None:
        """Primary path: multiple items with mixed scores."""
        items = [
            MagicMock(title="High", summary="very relevant", external_id="1"),
            MagicMock(title="Low", summary="irrelevant", external_id="2"),
            MagicMock(title="Medium", summary="somewhat relevant", external_id="3"),
        ]

        with patch(
            "app.channel.llm_client.openrouter_chat_completion",
            new_callable=AsyncMock,
            return_value=json.dumps({"0": 9, "1": 2, "2": 6}),
        ):
            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            assert len(result) == 2
            assert result[0].title == "High"
            assert result[1].title == "Medium"

    async def test_fallback_on_batch_failure(self) -> None:
        """When batch openrouter_chat_completion fails, falls back to per-item screening."""
        items = [MagicMock(title="Test", summary="content", external_id="1")]

        mock_result = MagicMock()
        mock_result.output = "8"

        with (
            patch(
                "app.channel.llm_client.openrouter_chat_completion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
            patch("app.channel.generator._create_screening_agent") as mock_agent_factory,
            patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_factory.return_value = mock_agent

            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            # Fallback path should still return the item
            assert len(result) == 1
            mock_agent_factory.assert_called_once()

    async def test_fallback_score_parsing_fraction(self) -> None:
        """Fallback path: when LLM returns '7/10', the regex extracts 7."""
        items = [MagicMock(title="Test", summary="content", external_id="1")]

        mock_result = MagicMock()
        mock_result.output = "7/10"

        with (
            patch(
                "app.channel.llm_client.openrouter_chat_completion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("batch failed"),
            ),
            patch("app.channel.generator._create_screening_agent") as mock_agent_factory,
            patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_factory.return_value = mock_agent

            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            assert len(result) == 1

    async def test_fallback_exception_per_item_continues(self) -> None:
        """Fallback path: per-item errors are caught; remaining items still screened."""
        items = [
            MagicMock(title="Fail", summary="will fail", external_id="1"),
            MagicMock(title="Pass", summary="will pass", external_id="2"),
        ]

        mock_result_ok = MagicMock()
        mock_result_ok.output = "8"

        with (
            patch(
                "app.channel.llm_client.openrouter_chat_completion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("batch failed"),
            ),
            patch("app.channel.generator._create_screening_agent") as mock_agent_factory,
            patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=[Exception("LLM error"), mock_result_ok])
            mock_agent_factory.return_value = mock_agent

            result = await screen_items(items, api_key="k", model="m", threshold=5)  # type: ignore[arg-type]
            # First item failed, second passed
            assert len(result) == 1
            assert result[0].title == "Pass"


# ---------------------------------------------------------------------------
# generate_post
# ---------------------------------------------------------------------------


class TestGeneratePost:
    async def test_empty_items_returns_none(self) -> None:
        result = await generate_post([], api_key="k", model="m")
        assert result is None

    async def test_uses_first_item_only(self) -> None:
        """generate_post always uses items[0] regardless of list length."""
        items = [
            MagicMock(title="First", body="First content", url="https://example.com/1"),
            MagicMock(title="Second", body="Second content", url="https://example.com/2"),
        ]

        mock_post = MagicMock()
        mock_post.text = "Generated text"
        mock_post.image_url = None
        mock_post.image_urls = []

        mock_result = MagicMock()
        mock_result.output = mock_post

        with (
            patch("app.channel.generator._create_generation_agent") as mock_agent_factory,
            patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
            patch("app.channel.images.find_images_for_post", new=AsyncMock(return_value=[])),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_factory.return_value = mock_agent

            result = await generate_post(items, api_key="k", model="m")  # type: ignore[arg-type]
            assert result is not None

            # Verify the prompt only contains the first item
            call_args = mock_agent.run.call_args
            prompt = call_args.args[0] if call_args.args else call_args.kwargs.get("user_prompt", "")
            assert "First" in prompt
            assert "Second" not in prompt


# ---------------------------------------------------------------------------
# enforce_footer_and_length
# ---------------------------------------------------------------------------


class TestEnforceFooterAndLength:
    def test_appends_footer_when_missing(self) -> None:
        from app.channel.generator import enforce_footer_and_length

        result = enforce_footer_and_length("Hello world", "——\nFooter")
        assert result.endswith("——\nFooter")

    def test_preserves_footer_when_present(self) -> None:
        from app.channel.generator import enforce_footer_and_length

        text = "Hello world\n\n——\nFooter"
        result = enforce_footer_and_length(text, "——\nFooter")
        assert result.count("——\nFooter") == 1

    def test_truncates_to_max_length(self) -> None:
        from app.channel.generator import enforce_footer_and_length

        long_text = "A" * 1000
        footer = "——\nFooter"
        result = enforce_footer_and_length(long_text, footer, max_length=200)
        assert len(result) <= 200
        assert result.endswith(footer)

    def test_uses_default_footer_when_empty(self) -> None:
        from app.channel.generator import DEFAULT_FOOTER, enforce_footer_and_length

        result = enforce_footer_and_length("Hello", "")
        assert DEFAULT_FOOTER in result
