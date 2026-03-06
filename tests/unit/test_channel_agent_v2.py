"""Tests for Channel Agent v2 — review flow, source management, feedback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from app.agent.channel.generator import GeneratedPost
from app.agent.channel.sources import ContentItem
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import ChannelPost, ChannelSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db_engine():  # type: ignore[misc]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def session_maker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture
def sample_content_items() -> list[ContentItem]:
    return [
        ContentItem(
            source_url="https://example.com/feed",
            external_id="item1",
            title="Test Article One",
            body="Body of article one about Czech universities.",
            url="https://example.com/article1",
        ),
        ContentItem(
            source_url="https://example.com/feed",
            external_id="item2",
            title="Test Article Two",
            body="Body of article two about student visas.",
            url="https://example.com/article2",
        ),
    ]


@pytest.fixture
def sample_post() -> GeneratedPost:
    return GeneratedPost(
        text="<b>Test Post</b>\n\nThis is a test post about Czech universities.\n\n#education #czech",
        is_sensitive=False,
    )


@pytest.fixture
def mock_bot() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_httpx_client():
    """Reusable mock for httpx.AsyncClient context manager."""

    def _make(response_content: str | None = None, *, raise_error: bool = False):
        mock_client = AsyncMock()
        if raise_error:
            mock_client.post.side_effect = Exception("API error")
        else:
            mock_response = MagicMock()
            mock_response.json.return_value = {"choices": [{"message": {"content": response_content or ""}}]}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    return _make


# ── ChannelPost model tests ──────────────────────────────────────────


class TestChannelPostModel:
    async def test_create_post(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test_channel",
                external_id="ext123",
                title="Test Post",
                post_text="<b>Hello</b>",
                status="draft",
            )
            session.add(post)
            await session.commit()

            result = await session.execute(select(ChannelPost))
            saved = result.scalar_one()
            assert saved.channel_id == "@test_channel"
            assert saved.status == "draft"
            assert saved.title == "Test Post"

    async def test_approve_sets_status_and_message_id(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="e1", title="T", post_text="text")
            session.add(post)
            await session.flush()

            post.approve(message_id=42)
            assert post.status == "approved"
            assert post.telegram_message_id == 42
            await session.commit()

    async def test_reject_sets_status_and_feedback(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="e1", title="T", post_text="text")
            session.add(post)
            await session.flush()

            post.reject("Too boring")
            assert post.status == "rejected"
            assert post.admin_feedback == "Too boring"
            await session.commit()

    async def test_update_text_resets_to_draft(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="e1", title="T", post_text="old", status="approved")
            session.add(post)
            await session.flush()

            post.update_text("new text")
            assert post.post_text == "new text"
            assert post.status == "draft"

    async def test_source_items_json(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        sources = [{"title": "Art", "url": "https://x.com/art"}]
        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="e1",
                title="T",
                post_text="text",
                source_items=sources,
            )
            session.add(post)
            await session.commit()

        async with session_maker() as session:
            result = await session.execute(select(ChannelPost))
            saved = result.scalar_one()
            assert saved.source_items == sources
            assert saved.source_items[0]["title"] == "Art"


# ── ChannelSource model tests ────────────────────────────────────────


class TestChannelSourceModel:
    async def test_create_source(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(
                channel_id="@test",
                url="https://example.com/feed",
                title="Example Feed",
                added_by="agent",
            )
            session.add(source)
            await session.commit()

            result = await session.execute(select(ChannelSource))
            saved = result.scalar_one()
            assert saved.url == "https://example.com/feed"
            assert saved.enabled is True
            assert saved.error_count == 0

    async def test_record_success_resets_errors(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            source.error_count = 3
            session.add(source)
            await session.flush()

            source.record_success()
            assert source.error_count == 0
            assert source.last_fetched_at is not None

    async def test_record_error_increments_and_disables(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            session.add(source)
            await session.flush()

            for i in range(5):
                source.record_error(f"error {i}")

            assert source.error_count == 5
            assert source.enabled is False
            assert source.last_error == "error 4"


# ── Source manager tests ─────────────────────────────────────────────


class TestSourceManager:
    async def test_add_source(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source

        result = await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        assert result is True

        async with session_maker() as session:
            sources = (await session.execute(select(ChannelSource))).scalars().all()
            assert len(sources) == 1
            assert sources[0].url == "https://feed.example.com/rss"

    async def test_add_duplicate_source_returns_false(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source

        await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        result = await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        assert result is False

    async def test_get_active_sources(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, get_active_sources

        await add_source(session_maker, "@ch", "https://active.com/feed")
        # Add and disable a source
        await add_source(session_maker, "@ch", "https://broken.com/feed")
        async with session_maker() as session:
            res = await session.execute(select(ChannelSource).where(ChannelSource.url == "https://broken.com/feed"))
            source = res.scalar_one()
            source.enabled = False
            await session.commit()

        active = await get_active_sources(session_maker, "@ch")
        assert len(active) == 1
        assert active[0].url == "https://active.com/feed"

    async def test_remove_source(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, remove_source

        await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        result = await remove_source(session_maker, "https://feed.example.com/rss")
        assert result is True

        async with session_maker() as session:
            count = len((await session.execute(select(ChannelSource))).scalars().all())
            assert count == 0

    async def test_remove_nonexistent_returns_false(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import remove_source

        result = await remove_source(session_maker, "https://nope.com/feed")
        assert result is False

    async def test_record_fetch_success(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, record_fetch_success

        await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        await record_fetch_success(session_maker, "https://feed.example.com/rss")

        async with session_maker() as session:
            source = (await session.execute(select(ChannelSource))).scalar_one()
            assert source.error_count == 0
            assert source.last_fetched_at is not None

    async def test_record_fetch_error_auto_disables(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, record_fetch_error

        await add_source(session_maker, "@ch", "https://feed.example.com/rss")
        for i in range(5):
            await record_fetch_error(session_maker, "https://feed.example.com/rss", f"err{i}")

        async with session_maker() as session:
            source = (await session.execute(select(ChannelSource))).scalar_one()
            assert source.enabled is False
            assert source.error_count == 5

    async def test_seed_sources_from_env(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import seed_sources_from_env

        added = await seed_sources_from_env(session_maker, "@ch", ["https://a.com/feed", "https://b.com/feed"])
        assert added == 2

        # Second seed should add 0
        added2 = await seed_sources_from_env(session_maker, "@ch", ["https://a.com/feed", "https://b.com/feed"])
        assert added2 == 0


# ── Review flow tests ────────────────────────────────────────────────


class TestReviewFlow:
    async def test_build_review_keyboard(self) -> None:
        from app.agent.channel.review import _build_review_keyboard

        kb = _build_review_keyboard(42)
        assert len(kb.inline_keyboard) == 2
        assert len(kb.inline_keyboard[0]) == 3  # Approve, Reject, Regen
        assert len(kb.inline_keyboard[1]) == 3  # Shorter, Longer, Translate
        assert kb.inline_keyboard[0][0].callback_data == "chpost:approve:42"
        assert kb.inline_keyboard[0][1].callback_data == "chpost:reject:42"

    async def test_format_review_message_without_sources(self) -> None:
        from app.agent.channel.review import _format_review_message

        msg = _format_review_message("<b>Hello</b>")
        assert "<b>Hello</b>" in msg
        assert "Reply to this message" in msg

    async def test_format_review_message_with_sources(self, sample_content_items: list[ContentItem]) -> None:
        from app.agent.channel.review import _format_review_message

        msg = _format_review_message("<b>Hello</b>", sample_content_items)
        assert "Sources:" in msg
        assert "Test Article One" in msg

    async def test_send_for_review(
        self,
        mock_bot: AsyncMock,
        sample_post: GeneratedPost,
        sample_content_items: list[ContentItem],
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import send_for_review

        mock_bot.send_message.return_value = MagicMock(message_id=100)

        post_id = await send_for_review(
            bot=mock_bot,
            review_chat_id=-1001234,
            channel_id="@test",
            post=sample_post,
            source_items=sample_content_items,
            session_maker=session_maker,
        )

        assert post_id is not None
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == -1001234
        assert call_kwargs["parse_mode"] == "HTML"

        # Verify DB record
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.channel_id == "@test"
            assert saved.status == "draft"
            assert saved.review_message_id == 100
            assert saved.source_items is not None
            assert len(saved.source_items) == 2

    async def test_handle_approve(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_approve

        # Create a post first
        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="Test",
                post_text="<b>Hello</b>",
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        mock_bot.send_message.return_value = MagicMock(message_id=200)

        result = await handle_approve(mock_bot, post_id, "@target_channel", session_maker)
        assert "Published" in result

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.status == "approved"
            assert saved.telegram_message_id == 200

    async def test_handle_approve_already_approved(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_approve

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text", status="approved")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_approve(mock_bot, post_id, "@ch", session_maker)
        assert result == "Already published."
        mock_bot.send_message.assert_not_called()

    async def test_handle_approve_post_not_found(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_approve

        result = await handle_approve(mock_bot, 999, "@ch", session_maker)
        assert result == "Post not found."

    async def test_handle_reject(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.review import handle_reject

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_reject(post_id, session_maker, reason="Bad quality")
        assert result == "Post rejected."

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.status == "rejected"
            assert saved.admin_feedback == "Bad quality"

    async def test_handle_reject_not_found(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.review import handle_reject

        result = await handle_reject(999, session_maker)
        assert result == "Post not found."

    async def test_handle_reject_without_reason(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.review import handle_reject

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_reject(post_id, session_maker)
        assert result == "Post rejected."

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.admin_feedback is None

    async def test_handle_approve_publish_fails(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_approve

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        mock_bot.send_message.side_effect = Exception("Telegram API error")
        result = await handle_approve(mock_bot, post_id, "@ch", session_maker)
        assert result == "Failed to publish."

    async def test_send_for_review_bot_error_returns_none(
        self,
        mock_bot: AsyncMock,
        sample_post: GeneratedPost,
        sample_content_items: list[ContentItem],
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import send_for_review

        mock_bot.send_message.side_effect = Exception("Bot error")

        post_id = await send_for_review(
            bot=mock_bot,
            review_chat_id=-1001234,
            channel_id="@test",
            post=sample_post,
            source_items=sample_content_items,
            session_maker=session_maker,
        )
        assert post_id is None

    async def test_send_for_review_empty_sources(
        self,
        mock_bot: AsyncMock,
        sample_post: GeneratedPost,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import send_for_review

        mock_bot.send_message.return_value = MagicMock(message_id=101)

        post_id = await send_for_review(
            bot=mock_bot,
            review_chat_id=-1001234,
            channel_id="@test",
            post=sample_post,
            source_items=[],
            session_maker=session_maker,
        )
        assert post_id is not None

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.title == "Generated post"

    async def test_handle_edit_request(
        self,
        mock_bot: AsyncMock,
        mock_httpx_client: object,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_edit_request

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="<b>Original</b>",
                review_message_id=50,
                review_chat_id=-100,
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client("<b>Edited</b>")  # type: ignore[operator]
            result = await handle_edit_request(
                mock_bot, post_id, "Make it shorter", "key", "model", -100, session_maker
            )

        assert result == "Post updated."
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.post_text == "<b>Edited</b>"
            assert saved.status == "draft"

    async def test_handle_edit_request_strips_code_fences(
        self,
        mock_bot: AsyncMock,
        mock_httpx_client: object,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_edit_request

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="old")
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client("```html\n<b>New</b>\n```")  # type: ignore[operator]
            result = await handle_edit_request(mock_bot, post_id, "edit", "key", "model", -100, session_maker)

        assert result == "Post updated."
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.post_text == "<b>New</b>"

    async def test_handle_edit_request_not_found(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_edit_request

        result = await handle_edit_request(mock_bot, 999, "edit", "key", "model", -100, session_maker)
        assert result == "Post not found."

    async def test_handle_edit_request_api_error(
        self,
        mock_bot: AsyncMock,
        mock_httpx_client: object,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_edit_request

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="old")
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client(raise_error=True)  # type: ignore[operator]
            result = await handle_edit_request(mock_bot, post_id, "edit", "key", "model", -100, session_maker)

        assert result == "Edit failed."

    async def test_handle_regen(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="old",
                source_items=[{"title": "Article", "url": "https://x.com/a", "source_url": "https://x.com/feed"}],
                review_message_id=50,
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("app.agent.channel.generator.generate_post", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = GeneratedPost(text="<b>Regenerated</b>", is_sensitive=False)
            result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)

        assert result == "Post regenerated."
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost))).scalar_one()
            assert saved.post_text == "<b>Regenerated</b>"

    async def test_handle_regen_no_sources(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="old", source_items=None)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)
        assert result == "No source data to regenerate from."

    async def test_handle_regen_not_found(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_regen

        result = await handle_regen(mock_bot, 999, "key", "model", "Russian", -100, session_maker)
        assert result == "Post not found."

    async def test_handle_regen_generation_fails(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="old",
                source_items=[{"title": "Art", "url": "https://x.com", "source_url": "https://x.com/feed"}],
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("app.agent.channel.generator.generate_post", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = None
            result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)

        assert result == "Regeneration failed."


# ── ChannelSource enable/disable tests ───────────────────────────────


class TestChannelSourceEnableDisable:
    async def test_enable_resets_error_count(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            source.error_count = 4
            source.enabled = False
            session.add(source)
            await session.flush()

            source.enable()
            assert source.enabled is True
            assert source.error_count == 0

    async def test_disable(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            session.add(source)
            await session.flush()

            source.disable()
            assert source.enabled is False

    async def test_error_at_boundary_still_enabled(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            session.add(source)
            await session.flush()

            for i in range(4):
                source.record_error(f"err {i}")

            assert source.error_count == 4
            assert source.enabled is True  # Not yet disabled at 4


# ── Source discovery tests ───────────────────────────────────────────


class TestSourceDiscovery:
    async def test_validate_feed_success(self) -> None:
        from app.agent.channel.source_discovery import validate_feed

        with patch("app.agent.channel.source_discovery.fetch_rss", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [ContentItem(source_url="url", external_id="1", title="T", body="B")]
            result = await validate_feed("https://example.com/feed")
            assert result is True

    async def test_validate_feed_empty(self) -> None:
        from app.agent.channel.source_discovery import validate_feed

        with patch("app.agent.channel.source_discovery.fetch_rss", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            result = await validate_feed("https://broken.com/feed")
            assert result is False

    async def test_validate_feed_error(self) -> None:
        from app.agent.channel.source_discovery import validate_feed

        with patch("app.agent.channel.source_discovery.fetch_rss", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")
            result = await validate_feed("https://error.com/feed")
            assert result is False

    async def test_discover_rss_feeds_parses_json(self, mock_httpx_client: object) -> None:
        from app.agent.channel.source_discovery import discover_rss_feeds

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client('[{"url": "https://a.com/feed", "title": "Feed A"}]')  # type: ignore[operator]
            feeds = await discover_rss_feeds("fake-key", "Czech education")
            assert len(feeds) == 1
            assert feeds[0]["url"] == "https://a.com/feed"

    async def test_discover_rss_feeds_handles_code_fences(self, mock_httpx_client: object) -> None:
        from app.agent.channel.source_discovery import discover_rss_feeds

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client('```json\n[{"url": "https://b.com/feed", "title": "B"}]\n```')  # type: ignore[operator]
            feeds = await discover_rss_feeds("fake-key", "query")
            assert len(feeds) == 1
            assert feeds[0]["url"] == "https://b.com/feed"

    async def test_discover_rss_feeds_api_error(self, mock_httpx_client: object) -> None:
        from app.agent.channel.source_discovery import discover_rss_feeds

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client(raise_error=True)  # type: ignore[operator]
            feeds = await discover_rss_feeds("fake-key", "query")
            assert feeds == []

    async def test_discover_and_add_sources(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_discovery import discover_and_add_sources

        with (
            patch("app.agent.channel.source_discovery.discover_rss_feeds", new_callable=AsyncMock) as mock_discover,
            patch("app.agent.channel.source_discovery.validate_feed", new_callable=AsyncMock) as mock_validate,
        ):
            mock_discover.return_value = [
                {"url": "https://valid.com/feed", "title": "Valid"},
                {"url": "https://broken.com/feed", "title": "Broken"},
            ]
            mock_validate.side_effect = [True, False]  # first valid, second broken

            added = await discover_and_add_sources("key", "@ch", "query", session_maker)
            assert added == 1

            async with session_maker() as session:
                sources = (await session.execute(select(ChannelSource))).scalars().all()
                assert len(sources) == 1
                assert sources[0].url == "https://valid.com/feed"


# ── Feedback summary tests ───────────────────────────────────────────


class TestFeedbackSummary:
    async def test_no_posts_returns_none(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.feedback import get_feedback_summary

        result = await get_feedback_summary(session_maker, "@ch", "key")
        assert result is None

    async def test_summarizes_feedback(
        self, session_maker: async_sessionmaker[AsyncSession], mock_httpx_client: object
    ) -> None:
        from app.agent.channel.feedback import get_feedback_summary

        async with session_maker() as session:
            for i in range(3):
                post = ChannelPost(
                    channel_id="@ch",
                    external_id=f"ext{i}",
                    title=f"Post {i}",
                    post_text=f"text {i}",
                    status="approved" if i < 2 else "rejected",
                )
                if i == 2:
                    post.admin_feedback = "Not relevant"
                session.add(post)
            await session.commit()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client("- Approves education content\n- Rejects offtopic")  # type: ignore[operator]
            summary = await get_feedback_summary(session_maker, "@ch", "key")
            assert summary is not None
            assert "Approves" in summary

            # Verify the LLM was called with context about approved/rejected posts
            call_args = mock_cls.return_value.post.call_args
            request_body = call_args[1]["json"]
            user_msg = request_body["messages"][1]["content"]
            assert "2 approved" in user_msg
            assert "1 rejected" in user_msg

    async def test_returns_none_on_llm_error(
        self, session_maker: async_sessionmaker[AsyncSession], mock_httpx_client: object
    ) -> None:
        from app.agent.channel.feedback import get_feedback_summary

        async with session_maker() as session:
            post = ChannelPost(channel_id="@ch", external_id="e1", title="T", post_text="t", status="approved")
            session.add(post)
            await session.commit()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client(raise_error=True)  # type: ignore[operator]
            result = await get_feedback_summary(session_maker, "@ch", "key")
            assert result is None


# ── Handler helper tests ─────────────────────────────────────────────


class TestHandlerHelpers:
    def test_extract_post_id(self) -> None:
        from app.presentation.telegram.handlers.channel_review import _extract_post_id

        assert _extract_post_id("chpost:approve:42", "chpost:approve:") == 42
        assert _extract_post_id("chpost:reject:100", "chpost:reject:") == 100
        assert _extract_post_id("chpost:approve:abc", "chpost:approve:") is None
        assert _extract_post_id("chpost:approve:", "chpost:approve:") is None


# ── ContentItem tests ────────────────────────────────────────────────


class TestContentItem:
    def test_summary_property(self) -> None:
        item = ContentItem(
            source_url="url",
            external_id="1",
            title="My Title",
            body="My body text",
        )
        assert item.summary == "My Title\nMy body text"

    def test_summary_truncates_body(self) -> None:
        item = ContentItem(
            source_url="url",
            external_id="1",
            title="Title",
            body="x" * 1000,
        )
        # "Title" + "\n" + 500 chars = 506
        assert len(item.summary) == len("Title") + 1 + 500

    def test_summary_with_empty_body(self) -> None:
        item = ContentItem(
            source_url="url",
            external_id="1",
            title="Title Only",
            body="",
        )
        assert item.summary == "Title Only"
