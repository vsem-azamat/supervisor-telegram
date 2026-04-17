"""Tests for Burr-based channel content pipeline workflow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.channel.config import ChannelAgentSettings
from app.agent.channel.sources import ContentItem
from app.agent.channel.workflow import (
    _has_content,
    _has_post,
    _has_relevant,
    _has_review_channel,
    _is_approved,
    _is_rejected,
    build_content_pipeline_graph,
    create_pipeline_app,
)
from app.infrastructure.db.models import Channel
from burr.core import State

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_channel(**kwargs: Any) -> Channel:
    defaults: dict[str, Any] = {
        "telegram_id": -1001234567890,
        "name": "Test Channel",
        "description": "Test channel",
        "language": "en",
        "review_chat_id": -1009999999999,
        "max_posts_per_day": 3,
    }
    defaults.update(kwargs)
    return Channel(**defaults)


@pytest.fixture
def channel() -> Channel:
    return _make_channel()


@pytest.fixture
def channel_no_review() -> Channel:
    return _make_channel(review_chat_id=None)


@pytest.fixture
def agent_settings() -> ChannelAgentSettings:
    return ChannelAgentSettings(
        enabled=True,
        discovery_enabled=False,
        source_discovery_enabled=False,
    )


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message.return_value = msg
    return bot


@pytest.fixture
def mock_session_maker() -> MagicMock:
    maker = MagicMock()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    maker.return_value = session
    maker._mock_session = session
    return maker


@pytest.fixture
def sample_items() -> list[ContentItem]:
    return [
        ContentItem(
            source_url="https://example.com/feed",
            external_id="item1",
            title="Test Article",
            body="Body about Czech universities.",
            url="https://example.com/article1",
        ),
    ]


# ---------------------------------------------------------------------------
# Graph structure tests
# ---------------------------------------------------------------------------


class TestGraphDefinition:
    def test_graph_builds_successfully(self):
        graph = build_content_pipeline_graph()
        assert graph is not None

    def test_graph_has_all_actions(self):
        graph = build_content_pipeline_graph()
        action_names = {a.name for a in graph.actions}
        expected = {
            "fetch_sources",
            "split_and_enrich_topics",
            "screen_content",
            "generate_post",
            "send_for_review",
            "await_review",
            "publish_post",
            "handle_rejection",
        }
        assert expected.issubset(action_names)

    def test_graph_has_transitions(self):
        graph = build_content_pipeline_graph()
        # The pipeline defines exactly 14 transitions (verified against workflow.py)
        assert len(graph.transitions) == 14


# ---------------------------------------------------------------------------
# Transition guard tests
# ---------------------------------------------------------------------------


class TestTransitionGuards:
    def test_has_content_true(self, sample_items):
        state = State({"content_items": sample_items})
        assert _has_content(state) is True

    def test_has_content_false_empty(self):
        state = State({"content_items": []})
        assert _has_content(state) is False

    def test_has_content_false_none(self):
        state = State({})
        assert _has_content(state) is False

    def test_has_relevant_true(self, sample_items):
        state = State({"relevant_items": sample_items})
        assert _has_relevant(state) is True

    def test_has_relevant_false(self):
        state = State({"relevant_items": []})
        assert _has_relevant(state) is False

    def test_has_post_true(self):
        state = State({"generated_post": {"text": "Hello", "is_sensitive": False}})
        assert _has_post(state) is True

    def test_has_post_false(self):
        state = State({"generated_post": None})
        assert _has_post(state) is False

    def test_has_review_channel_true(self, channel, agent_settings):
        state = State({"channel": channel, "config": agent_settings})
        assert _has_review_channel(state) is True

    def test_has_review_channel_false(self, channel_no_review, agent_settings):
        state = State({"channel": channel_no_review, "config": agent_settings})
        assert _has_review_channel(state) is False

    def test_is_approved(self):
        assert _is_approved(State({"review_decision": "approved"})) is True
        assert _is_approved(State({"review_decision": "rejected"})) is False
        assert _is_approved(State({"review_decision": None})) is False

    def test_is_rejected(self):
        assert _is_rejected(State({"review_decision": "rejected"})) is True
        assert _is_rejected(State({"review_decision": "approved"})) is False


# ---------------------------------------------------------------------------
# Action tests (individual actions with mocked deps)
# ---------------------------------------------------------------------------


class TestFetchSourcesAction:
    async def test_fetch_returns_items(self, agent_settings, channel, mock_session_maker):
        from app.agent.channel.workflow import fetch_sources

        mock_items = [
            ContentItem(
                source_url="https://test.com",
                external_id="ext1",
                title="Test",
                body="Body",
                url="https://test.com/1",
            )
        ]

        with (
            patch("app.agent.channel.source_manager.get_active_sources", return_value=[]),
            patch("app.agent.channel.discovery.discover_content", return_value=mock_items),
        ):
            agent_settings.discovery_enabled = True

            state = State(
                {
                    "channel_id": -1001234567890,
                    "config": agent_settings,
                    "channel": channel,
                    "api_key": "test-key",
                    "session_maker": mock_session_maker,
                    "content_items": [],
                    "error": None,
                }
            )

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session_maker._mock_session.execute = AsyncMock(return_value=mock_result)

            result = await fetch_sources(state)
            items = result["content_items"]
            assert len(items) == 1
            assert items[0].external_id == "ext1"
            assert result["error"] is None

    async def test_fetch_handles_error(self, agent_settings, channel, mock_session_maker):
        from app.agent.channel.workflow import fetch_sources

        with patch(
            "app.agent.channel.source_manager.get_active_sources",
            side_effect=RuntimeError("connection refused"),
        ):
            agent_settings.discovery_enabled = False
            state = State(
                {
                    "channel_id": -1001234567890,
                    "config": agent_settings,
                    "channel": channel,
                    "api_key": "test-key",
                    "session_maker": mock_session_maker,
                    "content_items": [],
                    "error": None,
                }
            )

            result = await fetch_sources(state)
            assert result["content_items"] == []
            assert result["error"] is not None
            assert "connection refused" in result["error"]


class TestScreenContentAction:
    async def test_screen_filters_relevant(self, agent_settings, channel, sample_items):
        from app.agent.channel.workflow import screen_content

        with patch("app.agent.channel.generator.screen_items", return_value=sample_items):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "channel": channel,
                    "relevant_items": [],
                    "error": None,
                }
            )
            result = await screen_content(state)
            assert len(result["relevant_items"]) == 1
            assert result["error"] is None

    async def test_screen_empty_input(self, agent_settings, channel):
        from app.agent.channel.workflow import screen_content

        state = State(
            {
                "content_items": [],
                "api_key": "test-key",
                "config": agent_settings,
                "channel": channel,
                "relevant_items": [],
                "error": None,
            }
        )
        result = await screen_content(state)
        assert result["relevant_items"] == []
        assert result["error"] is None

    async def test_screen_handles_screening_error(self, agent_settings, channel, sample_items):
        from app.agent.channel.exceptions import ScreeningError
        from app.agent.channel.workflow import screen_content

        with patch(
            "app.agent.channel.generator.screen_items",
            side_effect=ScreeningError("LLM down"),
        ):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "channel": channel,
                    "relevant_items": [],
                    "error": None,
                }
            )
            result = await screen_content(state)
            assert result["relevant_items"] == []
            assert "LLM down" in result["error"]

    async def test_screen_handles_generic_error(self, agent_settings, channel, sample_items):
        from app.agent.channel.workflow import screen_content

        with patch(
            "app.agent.channel.generator.screen_items",
            side_effect=RuntimeError("unexpected"),
        ):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "channel": channel,
                    "relevant_items": [],
                    "error": None,
                }
            )
            result = await screen_content(state)
            assert result["relevant_items"] == []
            assert result["error"] is not None


class TestSplitAndEnrichTopicsAction:
    async def test_enriches_items(self, agent_settings, channel, sample_items, mock_session_maker):
        from app.agent.channel.workflow import split_and_enrich_topics

        with (
            patch("app.agent.channel.topic_splitter.split_and_enrich", return_value=sample_items),
            patch("app.agent.channel.semantic_dedup.filter_semantic_duplicates", return_value=sample_items),
        ):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "k",
                    "brave_api_key": "",
                    "config": agent_settings,
                    "channel_id": -1001234567890,
                    "session_maker": mock_session_maker,
                }
            )
            result = await split_and_enrich_topics(state)
            assert len(result["content_items"]) == 1
            assert result["error"] is None

    async def test_empty_input_passthrough(self, agent_settings, mock_session_maker):
        from app.agent.channel.workflow import split_and_enrich_topics

        state = State(
            {
                "content_items": [],
                "api_key": "k",
                "brave_api_key": "",
                "config": agent_settings,
                "channel_id": -1001234567890,
                "session_maker": mock_session_maker,
            }
        )
        result = await split_and_enrich_topics(state)
        assert result["content_items"] == []

    async def test_split_error_falls_back_to_original(self, agent_settings, sample_items, mock_session_maker):
        from app.agent.channel.workflow import split_and_enrich_topics

        with (
            patch(
                "app.agent.channel.topic_splitter.split_and_enrich",
                side_effect=RuntimeError("split failed"),
            ),
            # Dedup is now mandatory — patch it so the split-fallback path is
            # exercised independently of the embedding API.
            patch("app.agent.channel.semantic_dedup.filter_semantic_duplicates", return_value=sample_items),
        ):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "k",
                    "brave_api_key": "",
                    "config": agent_settings,
                    "channel_id": -1001234567890,
                    "session_maker": mock_session_maker,
                }
            )
            result = await split_and_enrich_topics(state)
            # Original items preserved on split error; dedup still applied.
            assert len(result["content_items"]) == 1
            assert result["content_items"][0].external_id == "item1"

    async def test_dedup_api_failure_halts_cycle(self, agent_settings, sample_items, mock_session_maker):
        """When the embedding API is down, the cycle returns zero items rather
        than publishing unfiltered content."""
        from app.agent.channel.exceptions import EmbeddingError
        from app.agent.channel.workflow import split_and_enrich_topics

        with (
            patch("app.agent.channel.topic_splitter.split_and_enrich", return_value=sample_items),
            patch(
                "app.agent.channel.semantic_dedup.filter_semantic_duplicates",
                side_effect=EmbeddingError("api down"),
            ),
        ):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "k",
                    "brave_api_key": "",
                    "config": agent_settings,
                    "channel_id": -1001234567890,
                    "session_maker": mock_session_maker,
                }
            )
            result = await split_and_enrich_topics(state)
            assert result["content_items"] == []
            assert "embedding_unavailable" in (result["error"] or "")


class TestPublishPostAction:
    async def test_publish_post_missing_post_id(self, channel, mock_bot, mock_session_maker):
        from app.agent.channel.workflow import publish_post

        state = State(
            {
                "post_id": None,
                "channel_id": -1001234567890,
                "channel": channel,
                "publish_bot": mock_bot,
                "session_maker": mock_session_maker,
            }
        )
        result = await publish_post(state)
        assert result["error"] == "missing_post_id"

    async def test_publish_post_publish_error(self, channel, mock_bot, mock_session_maker):
        from app.agent.channel.exceptions import PublishError
        from app.agent.channel.workflow import publish_post

        with patch(
            "app.agent.channel.review.handle_approve",
            side_effect=PublishError("Telegram API rejected"),
        ):
            state = State(
                {
                    "post_id": 42,
                    "channel_id": -1001234567890,
                    "channel": channel,
                    "publish_bot": mock_bot,
                    "session_maker": mock_session_maker,
                }
            )
            result = await publish_post(state)
            assert result["result_message"] == "publish_failed"
            assert "Telegram API rejected" in result["error"]


class TestGeneratePostAction:
    async def test_generate_produces_post(self, agent_settings, channel, mock_session_maker, sample_items):
        from app.agent.channel.generator import GeneratedPost
        from app.agent.channel.workflow import generate_post

        mock_post = GeneratedPost(text="**Test Post**", is_sensitive=False)

        with (
            patch("app.agent.channel.generator.generate_post", return_value=mock_post),
            patch("app.agent.channel.feedback.get_feedback_summary", return_value=None),
            # Pre-generation dedup hits the embeddings API; stub out so the test
            # stays isolated from network failures.
            patch("app.agent.channel.semantic_dedup.find_nearest_posts", return_value=[]),
        ):
            state = State(
                {
                    "relevant_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "channel": channel,
                    "channel_id": -1001234567890,
                    "session_maker": mock_session_maker,
                    "generated_post": None,
                    "error": None,
                }
            )
            result = await generate_post(state)
            assert result["generated_post"] is not None
            assert result["generated_post"]["text"] == "**Test Post**"
            assert result["error"] is None


# ---------------------------------------------------------------------------
# App factory test
# ---------------------------------------------------------------------------


class TestAppFactory:
    def test_creates_app(self, channel, agent_settings, mock_bot, mock_session_maker):
        app = create_pipeline_app(
            channel_id=-1001234567890,
            session_maker=mock_session_maker,
            publish_bot=mock_bot,
            api_key="test-key",
            config=agent_settings,
            channel=channel,
        )
        assert app is not None
        assert app.graph is not None
        assert app.state["channel_id"] == -1001234567890
        assert app.state["api_key"] == "test-key"

    def test_creates_app_with_resume_state(self, channel, agent_settings, mock_bot, mock_session_maker):
        app = create_pipeline_app(
            channel_id=-1001234567890,
            session_maker=mock_session_maker,
            publish_bot=mock_bot,
            api_key="test-key",
            config=agent_settings,
            channel=channel,
            resume_state={"review_decision": "approved", "post_id": 42},
            entrypoint="await_review",
        )
        assert app is not None
        assert app.graph is not None
        assert app.state["review_decision"] == "approved"
        assert app.state["post_id"] == 42


# ---------------------------------------------------------------------------
# Full pipeline integration tests (mocked externals)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    async def test_pipeline_no_content_stops_early(self, channel, agent_settings, mock_bot, mock_session_maker):
        with (
            patch("app.agent.channel.source_manager.get_active_sources", return_value=[]),
            patch("app.agent.channel.discovery.discover_content", return_value=[]),
        ):
            agent_settings.discovery_enabled = True
            app = create_pipeline_app(
                channel_id=-1001234567890,
                session_maker=mock_session_maker,
                publish_bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
            )
            action_obj, _result, state = await app.arun(halt_after=["await_review", "done"])
            assert action_obj.name == "done"
            assert state["content_items"] == []

    async def test_pipeline_halts_at_review(self, channel, agent_settings, mock_bot, mock_session_maker, sample_items):
        from app.agent.channel.generator import GeneratedPost

        mock_post = GeneratedPost(text="**Post**", is_sensitive=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session_maker._mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.agent.channel.source_manager.get_active_sources", return_value=[]),
            patch("app.agent.channel.discovery.discover_content", return_value=sample_items),
            patch("app.agent.channel.generator.screen_items", return_value=sample_items),
            patch("app.agent.channel.generator.generate_post", return_value=mock_post),
            patch("app.agent.channel.feedback.get_feedback_summary", return_value=None),
            patch("app.agent.channel.review.send_for_review", return_value=99),
            # Embeddings are mandatory; stub the dedup helpers so the pipeline
            # runs end-to-end without hitting the embeddings API.
            patch("app.agent.channel.semantic_dedup.filter_semantic_duplicates", return_value=sample_items),
            patch("app.agent.channel.semantic_dedup.find_nearest_posts", return_value=[]),
        ):
            agent_settings.discovery_enabled = True
            app = create_pipeline_app(
                channel_id=-1001234567890,
                session_maker=mock_session_maker,
                publish_bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
            )
            action_obj, _result, state = await app.arun(halt_after=["await_review", "done"])
            assert action_obj.name == "await_review"
            assert state["post_id"] == 99

    async def test_pipeline_resume_approve(self, channel, agent_settings, mock_bot, mock_session_maker):
        with patch("app.agent.channel.review.handle_approve", return_value="Published! (msg #42)"):
            app = create_pipeline_app(
                channel_id=-1001234567890,
                session_maker=mock_session_maker,
                publish_bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
                resume_state={"review_decision": "approved", "post_id": 99},
                entrypoint="await_review",
            )
            action_obj, _result, state = await app.arun(halt_after=["done"])
            assert state["result_message"] == "Published! (msg #42)"

    async def test_pipeline_resume_reject(self, channel, agent_settings, mock_bot, mock_session_maker):
        with patch("app.agent.channel.review.handle_reject", return_value="Post rejected."):
            app = create_pipeline_app(
                channel_id=-1001234567890,
                session_maker=mock_session_maker,
                publish_bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
                resume_state={"review_decision": "rejected", "post_id": 99},
                entrypoint="await_review",
            )
            action_obj, _result, state = await app.arun(halt_after=["done"])
            assert state["result_message"] == "Post rejected."

    async def test_pipeline_direct_publish_no_review_channel(
        self, channel_no_review, agent_settings, mock_bot, mock_session_maker, sample_items
    ):
        """T3: Direct publish path (no review channel) goes straight to done."""
        from app.agent.channel.generator import GeneratedPost

        mock_post = GeneratedPost(text="**Post**", is_sensitive=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session_maker._mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.agent.channel.source_manager.get_active_sources", return_value=[]),
            patch("app.agent.channel.discovery.discover_content", return_value=sample_items),
            patch("app.agent.channel.topic_splitter.split_and_enrich", return_value=sample_items),
            patch("app.agent.channel.semantic_dedup.filter_semantic_duplicates", return_value=sample_items),
            patch("app.agent.channel.semantic_dedup.find_nearest_posts", return_value=[]),
            patch("app.agent.channel.generator.screen_items", return_value=sample_items),
            patch("app.agent.channel.generator.generate_post", return_value=mock_post),
            patch("app.agent.channel.feedback.get_feedback_summary", return_value=None),
            patch("app.agent.channel.publisher.publish_post", return_value=77),
        ):
            agent_settings.discovery_enabled = True
            app = create_pipeline_app(
                channel_id=-1001234567890,
                session_maker=mock_session_maker,
                publish_bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel_no_review,
            )
            action_obj, _result, state = await app.arun(halt_after=["await_review", "done"])
            assert action_obj.name == "done"
            assert "published_directly:77" in state["result_message"]
