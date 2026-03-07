"""Tests for Burr-based channel content pipeline workflow."""

from __future__ import annotations

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


def _make_channel(**kwargs: object) -> Channel:
    defaults = {
        "telegram_id": "-1001234567890",
        "name": "Test Channel",
        "description": "Test channel",
        "language": "en",
        "review_chat_id": -1009999999999,
        "max_posts_per_day": 3,
    }
    defaults.update(kwargs)
    return Channel(**defaults)  # type: ignore[arg-type]


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
        channel_id=-1001234567890,
        review_chat_id=0,
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
        assert len(graph.transitions) > 0


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
    @pytest.mark.asyncio
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
                    "channel_id": "test_channel",
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

    @pytest.mark.asyncio
    async def test_fetch_handles_error(self, agent_settings, channel, mock_session_maker):
        from app.agent.channel.workflow import fetch_sources

        with patch(
            "app.agent.channel.source_manager.get_active_sources",
            side_effect=RuntimeError("connection refused"),
        ):
            agent_settings.discovery_enabled = False
            state = State(
                {
                    "channel_id": "test_channel",
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
    @pytest.mark.asyncio
    async def test_screen_filters_relevant(self, agent_settings, sample_items):
        from app.agent.channel.workflow import screen_content

        with patch("app.agent.channel.generator.screen_items", return_value=sample_items):
            state = State(
                {
                    "content_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "relevant_items": [],
                    "error": None,
                }
            )
            result = await screen_content(state)
            assert len(result["relevant_items"]) == 1
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_screen_empty_input(self, agent_settings):
        from app.agent.channel.workflow import screen_content

        state = State(
            {"content_items": [], "api_key": "test-key", "config": agent_settings, "relevant_items": [], "error": None}
        )
        result = await screen_content(state)
        assert result["relevant_items"] == []
        assert result["error"] is None


class TestGeneratePostAction:
    @pytest.mark.asyncio
    async def test_generate_produces_post(self, agent_settings, channel, mock_session_maker, sample_items):
        from app.agent.channel.generator import GeneratedPost
        from app.agent.channel.workflow import generate_post

        mock_post = GeneratedPost(text="**Test Post**", is_sensitive=False)

        with (
            patch("app.agent.channel.generator.generate_post", return_value=mock_post),
            patch("app.agent.channel.feedback.get_feedback_summary", return_value=None),
        ):
            state = State(
                {
                    "relevant_items": sample_items,
                    "api_key": "test-key",
                    "config": agent_settings,
                    "channel": channel,
                    "channel_id": "test_channel",
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
            channel_id="test_channel",
            session_maker=mock_session_maker,
            bot=mock_bot,
            api_key="test-key",
            config=agent_settings,
            channel=channel,
        )
        assert app is not None

    def test_creates_app_with_resume_state(self, channel, agent_settings, mock_bot, mock_session_maker):
        app = create_pipeline_app(
            channel_id="test_channel",
            session_maker=mock_session_maker,
            bot=mock_bot,
            api_key="test-key",
            config=agent_settings,
            channel=channel,
            resume_state={"review_decision": "approved", "post_id": 42},
            entrypoint="await_review",
        )
        assert app is not None


# ---------------------------------------------------------------------------
# Full pipeline integration tests (mocked externals)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_no_content_stops_early(self, channel, agent_settings, mock_bot, mock_session_maker):
        with (
            patch("app.agent.channel.source_manager.get_active_sources", return_value=[]),
            patch("app.agent.channel.discovery.discover_content", return_value=[]),
        ):
            agent_settings.discovery_enabled = True
            app = create_pipeline_app(
                channel_id="test_channel",
                session_maker=mock_session_maker,
                bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
            )
            action_obj, _result, state = await app.arun(halt_after=["await_review", "done"])
            assert action_obj.name == "done"
            assert state["content_items"] == []

    @pytest.mark.asyncio
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
        ):
            agent_settings.discovery_enabled = True
            app = create_pipeline_app(
                channel_id="test_channel",
                session_maker=mock_session_maker,
                bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
            )
            action_obj, _result, state = await app.arun(halt_after=["await_review", "done"])
            assert action_obj.name == "await_review"
            assert state["post_id"] == 99

    @pytest.mark.asyncio
    async def test_pipeline_resume_approve(self, channel, agent_settings, mock_bot, mock_session_maker):
        with patch("app.agent.channel.review.handle_approve", return_value="Published! (msg #42)"):
            app = create_pipeline_app(
                channel_id="test_channel",
                session_maker=mock_session_maker,
                bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
                resume_state={"review_decision": "approved", "post_id": 99},
                entrypoint="await_review",
            )
            action_obj, _result, state = await app.arun(halt_after=["done"])
            assert state["result_message"] == "Published! (msg #42)"

    @pytest.mark.asyncio
    async def test_pipeline_resume_reject(self, channel, agent_settings, mock_bot, mock_session_maker):
        with patch("app.agent.channel.review.handle_reject", return_value="Post rejected."):
            app = create_pipeline_app(
                channel_id="test_channel",
                session_maker=mock_session_maker,
                bot=mock_bot,
                api_key="test-key",
                config=agent_settings,
                channel=channel,
                resume_state={"review_decision": "rejected", "post_id": 99},
                entrypoint="await_review",
            )
            action_obj, _result, state = await app.arun(halt_after=["done"])
            assert state["result_message"] == "Post rejected."
