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
            assert saved.source_items[0]["title"] == "Art"  # ty: ignore[not-subscriptable]


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
        from app.agent.channel.review import build_review_keyboard
        from app.presentation.telegram.utils.callback_data import ReviewAction

        kb = build_review_keyboard(42)
        assert len(kb.inline_keyboard) == 2
        assert len(kb.inline_keyboard[0]) == 4  # Approve, Schedule, Reject, Delete
        assert len(kb.inline_keyboard[1]) == 3  # Shorter, Longer, Regen
        assert kb.inline_keyboard[0][0].callback_data == ReviewAction(action="approve", post_id=42).pack()
        assert kb.inline_keyboard[0][1].callback_data == ReviewAction(action="schedule", post_id=42).pack()
        assert kb.inline_keyboard[0][2].callback_data == ReviewAction(action="reject", post_id=42).pack()
        assert kb.inline_keyboard[0][3].callback_data == ReviewAction(action="delete", post_id=42).pack()

    async def test_build_review_keyboard_with_channel_and_sources(self) -> None:
        from app.agent.channel.review import build_review_keyboard

        kb = build_review_keyboard(
            42,
            source_items=[{"title": "Article 1", "url": "https://example.com/1"}],
            channel_name="Test Channel",
            channel_username="test_channel",
        )
        # 2 action rows + channel row + source row
        assert len(kb.inline_keyboard) == 4
        # Row 3: channel
        assert kb.inline_keyboard[2][0].url == "https://t.me/test_channel"
        # Row 4: sources
        assert kb.inline_keyboard[3][0].url == "https://example.com/1"

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
        assert "entities" in call_kwargs  # entities-based formatting
        # CRITICAL: parse_mode=None must override bot's default parse_mode="HTML"
        # Without this, entities are silently ignored by Telegram
        assert call_kwargs.get("parse_mode") is None, (
            "parse_mode must be explicitly None to override bot default HTML parse_mode"
        )

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

    async def test_handle_delete(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_delete

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                review_chat_id=123,
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_delete(mock_bot, post_id, 123, 456, session_maker)
        assert result == "Post deleted."

        # Post should be gone from DB
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
            assert saved is None

        # Review message should have been deleted
        mock_bot.delete_message.assert_awaited_once_with(chat_id=123, message_id=456)

    async def test_handle_delete_not_found(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_delete

        result = await handle_delete(mock_bot, 999, 123, None, session_maker)
        assert result == "Post not found."

    async def test_handle_delete_already_published(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_delete

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            post.approve(100)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_delete(mock_bot, post_id, 123, 456, session_maker)
        assert result == "Already published — cannot delete."

        # Post should still exist
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
            assert saved is not None

    async def test_handle_delete_no_review_message(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_delete

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_delete(mock_bot, post_id, 123, None, session_maker)
        assert result == "Post deleted."
        mock_bot.delete_message.assert_not_awaited()

    async def test_handle_delete_message_delete_fails_gracefully(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        from app.agent.channel.review import handle_delete

        mock_bot.delete_message.side_effect = Exception("Telegram error")

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="ext1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        # Should still succeed even if message deletion fails
        result = await handle_delete(mock_bot, post_id, 123, 789, session_maker)
        assert result == "Post deleted."

        # Post should be gone
        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one_or_none()
            assert saved is None

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

        # parse_mode=None must be explicitly passed
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs.get("parse_mode") is None

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
            assert saved.post_text.startswith("<b>Edited</b>")
            assert "Konnekt" in saved.post_text
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
            assert saved.post_text.startswith("<b>New</b>")
            assert "Konnekt" in saved.post_text

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

    # ── Priority 2: Guard condition tests ──

    async def test_handle_approve_post_is_scheduled(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Approving a SCHEDULED post should return a specific message instead of publishing."""
        from app.agent.channel.review import handle_approve

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                status="scheduled",
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_approve(mock_bot, post_id, "@ch", session_maker)
        assert result == "Post is scheduled. Use 'Publish now' to send immediately."
        mock_bot.send_message.assert_not_called()

    async def test_handle_edit_request_already_approved(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Editing an APPROVED post should return an error."""
        from app.agent.channel.review import handle_edit_request

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                status="approved",
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_edit_request(mock_bot, post_id, "edit", "key", "model", -100, session_maker)
        assert result == "Already published — cannot edit."

    async def test_handle_edit_request_already_rejected(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Editing a REJECTED post should return an error."""
        from app.agent.channel.review import handle_edit_request

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                status="rejected",
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_edit_request(mock_bot, post_id, "edit", "key", "model", -100, session_maker)
        assert result == "Post was rejected — cannot edit."

    async def test_handle_regen_already_approved(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Regen on APPROVED post should return an error."""
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                status="approved",
                source_items=[{"title": "Art", "url": "https://x.com", "source_url": "https://x.com/feed"}],
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)
        assert result == "Already published — cannot regenerate."

    async def test_handle_regen_already_rejected(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Regen on REJECTED post should return an error."""
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="text",
                status="rejected",
                source_items=[{"title": "Art", "url": "https://x.com", "source_url": "https://x.com/feed"}],
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)
        assert result == "Post was rejected — cannot regenerate."

    # ── Priority 3: Review message update assertion ──

    async def test_handle_edit_request_updates_review_message(
        self,
        mock_bot: AsyncMock,
        mock_httpx_client: object,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """When review_message_id is set, edit should update the review message via _edit_review_message."""
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
        # Verify the review message was updated via edit_message_text
        mock_bot.edit_message_text.assert_called_once()
        edit_kwargs = mock_bot.edit_message_text.call_args[1]
        assert edit_kwargs["chat_id"] == -100
        assert edit_kwargs["message_id"] == 50
        # parse_mode=None must be passed for entities to work
        assert edit_kwargs.get("parse_mode") is None
        assert "entities" in edit_kwargs

    async def test_handle_regen_updates_review_message(
        self,
        mock_bot: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """When review_message_id is set, regen should update the review message."""
        from app.agent.channel.review import handle_regen

        async with session_maker() as session:
            post = ChannelPost(
                channel_id="@test",
                external_id="ext1",
                title="T",
                post_text="old",
                source_items=[{"title": "Article", "url": "https://x.com/a", "source_url": "https://x.com/feed"}],
                review_message_id=50,
                review_chat_id=-100,
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        with patch("app.agent.channel.generator.generate_post", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = GeneratedPost(text="<b>Regenerated</b>", is_sensitive=False)
            result = await handle_regen(mock_bot, post_id, "key", "model", "Russian", -100, session_maker)

        assert result == "Post regenerated."
        # Review message should be updated
        mock_bot.edit_message_text.assert_called_once()
        edit_kwargs = mock_bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == 50
        assert edit_kwargs.get("parse_mode") is None


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
            feeds = await discover_rss_feeds("fake-key", "Czech education", model="perplexity/sonar")
            assert len(feeds) == 1
            assert feeds[0]["url"] == "https://a.com/feed"

    async def test_discover_rss_feeds_handles_code_fences(self, mock_httpx_client: object) -> None:
        from app.agent.channel.source_discovery import discover_rss_feeds

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client('```json\n[{"url": "https://b.com/feed", "title": "B"}]\n```')  # type: ignore[operator]
            feeds = await discover_rss_feeds("fake-key", "query", model="perplexity/sonar")
            assert len(feeds) == 1
            assert feeds[0]["url"] == "https://b.com/feed"

    async def test_discover_rss_feeds_api_error(self, mock_httpx_client: object) -> None:
        from app.agent.channel.source_discovery import discover_rss_feeds

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_httpx_client(raise_error=True)  # type: ignore[operator]
            feeds = await discover_rss_feeds("fake-key", "query", model="perplexity/sonar")
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

            added = await discover_and_add_sources("key", "@ch", "query", session_maker, model="perplexity/sonar")
            assert added == 1

            async with session_maker() as session:
                sources = (await session.execute(select(ChannelSource))).scalars().all()
                assert len(sources) == 1
                assert sources[0].url == "https://valid.com/feed"


# ── Feedback summary tests ───────────────────────────────────────────


class TestFeedbackSummary:
    async def test_no_posts_returns_none(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.feedback import get_feedback_summary

        result = await get_feedback_summary(session_maker, "@ch", "key", model="google/gemini-3.1-flash-lite-preview")
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
            summary = await get_feedback_summary(
                session_maker, "@ch", "key", model="google/gemini-3.1-flash-lite-preview"
            )
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
            result = await get_feedback_summary(
                session_maker, "@ch", "key", model="google/gemini-3.1-flash-lite-preview"
            )
            assert result is None


# ── Handler helper tests ─────────────────────────────────────────────


class TestHandlerHelpers:
    def test_callback_data_factories(self) -> None:
        from app.presentation.telegram.utils.callback_data import PublishNow, ReviewAction, SchedulePick

        # ReviewAction pack/unpack
        packed = ReviewAction(action="approve", post_id=42).pack()
        assert "rv:" in packed
        unpacked = ReviewAction.unpack(packed)
        assert unpacked.action == "approve"
        assert unpacked.post_id == 42

        # SchedulePick
        sp = SchedulePick(post_id=42, ts=1234567890).pack()
        assert "rvsp:" in sp
        unpacked_sp = SchedulePick.unpack(sp)
        assert unpacked_sp.post_id == 42
        assert unpacked_sp.ts == 1234567890

        # PublishNow
        pn = PublishNow(post_id=42).pack()
        assert "rvpub:" in pn


# ── ContentItem tests ────────────────────────────────────────────────


class TestGeneratePostFeedbackContext:
    """Tests for feedback_context parameter in generate_post()."""

    async def test_generate_post_without_feedback_context(self, sample_content_items: list[ContentItem]) -> None:
        """generate_post works with feedback_context=None (default, existing behavior)."""
        from app.agent.channel.generator import generate_post

        mock_result = MagicMock()
        mock_result.output = GeneratedPost(text="<b>Post</b>", is_sensitive=False)

        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result

        with patch("app.agent.channel.generator._create_generation_agent", return_value=mock_agent):
            post = await generate_post(sample_content_items, api_key="key", model="model")

        assert post is not None
        # Footer is auto-appended if missing
        assert post.text.startswith("<b>Post</b>")
        assert "Konnekt" in post.text
        # Verify the prompt does NOT contain admin preferences
        call_args = mock_agent.run.call_args[0][0]
        assert "Admin preferences" not in call_args

    async def test_generate_post_with_feedback_context(self, sample_content_items: list[ContentItem]) -> None:
        """generate_post includes feedback context in the LLM prompt when provided."""
        from app.agent.channel.generator import generate_post

        mock_result = MagicMock()
        mock_result.output = GeneratedPost(text="<b>Post</b>", is_sensitive=False)

        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result

        feedback = "- Approves education content\n- Rejects memes"

        with patch("app.agent.channel.generator._create_generation_agent", return_value=mock_agent):
            post = await generate_post(
                sample_content_items,
                api_key="key",
                model="model",
                feedback_context=feedback,
            )

        assert post is not None
        call_args = mock_agent.run.call_args[0][0]
        assert "Admin preferences (use to guide your writing):" in call_args
        assert "Approves education content" in call_args
        assert "Rejects memes" in call_args

    async def test_generate_post_with_empty_string_feedback(self, sample_content_items: list[ContentItem]) -> None:
        """generate_post treats empty string feedback_context same as None."""
        from app.agent.channel.generator import generate_post

        mock_result = MagicMock()
        mock_result.output = GeneratedPost(text="<b>Post</b>", is_sensitive=False)

        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result

        with patch("app.agent.channel.generator._create_generation_agent", return_value=mock_agent):
            post = await generate_post(
                sample_content_items,
                api_key="key",
                model="model",
                feedback_context="",
            )

        assert post is not None
        call_args = mock_agent.run.call_args[0][0]
        assert "Admin preferences" not in call_args


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


# ── Relevance scoring tests ──────────────────────────────────────────


class TestRelevanceScoring:
    async def test_boost_relevance_increases_score(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            session.add(source)
            await session.flush()

            assert source.relevance_score == 1.0
            source.boost_relevance()
            assert abs(source.relevance_score - 1.1) < 1e-9

    async def test_boost_relevance_caps_at_2(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            source.relevance_score = 1.95
            session.add(source)
            await session.flush()

            source.boost_relevance()
            assert source.relevance_score == 2.0

            # Another boost should stay at 2.0
            source.boost_relevance()
            assert source.relevance_score == 2.0

    async def test_penalize_relevance_decreases_score(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            session.add(source)
            await session.flush()

            source.penalize_relevance()
            assert abs(source.relevance_score - 0.8) < 1e-9
            assert source.enabled is True

    async def test_penalize_relevance_floors_at_0(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            source.relevance_score = 0.1
            session.add(source)
            await session.flush()

            source.penalize_relevance()
            assert source.relevance_score == 0.0
            assert source.enabled is False

    async def test_penalize_relevance_auto_disables_below_03(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_maker() as session:
            source = ChannelSource(channel_id="@test", url="https://x.com/feed", added_by="test")
            source.relevance_score = 0.4
            session.add(source)
            await session.flush()

            source.penalize_relevance()
            # 0.4 - 0.2 = 0.2, which is < 0.3
            assert abs(source.relevance_score - 0.2) < 1e-9
            assert source.enabled is False

    async def test_update_source_relevance_approved(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, update_source_relevance

        await add_source(session_maker, "@ch", "https://good.com/feed")
        await update_source_relevance(session_maker, ["https://good.com/feed"], approved=True)

        async with session_maker() as session:
            source = (await session.execute(select(ChannelSource))).scalar_one()
            assert abs(source.relevance_score - 1.1) < 1e-9

    async def test_update_source_relevance_rejected(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        from app.agent.channel.source_manager import add_source, update_source_relevance

        await add_source(session_maker, "@ch", "https://bad.com/feed")
        await update_source_relevance(session_maker, ["https://bad.com/feed"], approved=False)

        async with session_maker() as session:
            source = (await session.execute(select(ChannelSource))).scalar_one()
            assert abs(source.relevance_score - 0.8) < 1e-9

    async def test_update_source_relevance_unknown_url_ignored(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        from app.agent.channel.source_manager import update_source_relevance

        # Should not raise
        await update_source_relevance(session_maker, ["https://nonexistent.com/feed"], approved=True)

    async def test_get_active_sources_ordered_by_relevance(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        from app.agent.channel.source_manager import get_active_sources

        async with session_maker() as session:
            s1 = ChannelSource(channel_id="@ch", url="https://low.com/feed", added_by="test")
            s1.relevance_score = 0.5
            s2 = ChannelSource(channel_id="@ch", url="https://high.com/feed", added_by="test")
            s2.relevance_score = 1.8
            s3 = ChannelSource(channel_id="@ch", url="https://mid.com/feed", added_by="test")
            s3.relevance_score = 1.0
            session.add_all([s1, s2, s3])
            await session.commit()

        sources = await get_active_sources(session_maker, "@ch")
        assert len(sources) == 3
        assert sources[0].url == "https://high.com/feed"
        assert sources[1].url == "https://mid.com/feed"
        assert sources[2].url == "https://low.com/feed"


# ── Cost Tracker Tests ───────────────────────────────────────────────


class TestCostTracker:
    """Tests for the LLM cost tracking module."""

    def setup_method(self) -> None:
        from app.agent.channel.cost_tracker import reset_usage_history

        reset_usage_history()

    def test_extract_usage_from_openrouter_response_valid(self) -> None:
        from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response

        response = {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }
        usage = extract_usage_from_openrouter_response(response, "perplexity/sonar", "discovery", "@mychannel")

        assert usage is not None
        assert usage.model == "perplexity/sonar"
        assert usage.operation == "discovery"
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.channel_id == "@mychannel"
        assert usage.estimated_cost_usd > 0

    def test_extract_usage_from_openrouter_response_missing_usage(self) -> None:
        from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response

        response = {"choices": [{"message": {"content": "hello"}}]}
        usage = extract_usage_from_openrouter_response(response, "perplexity/sonar", "discovery")
        assert usage is None

    def test_cost_estimation_known_model(self) -> None:
        from app.agent.channel.cost_tracker import _estimate_cost

        # google/gemini-2.0-flash-001: input=0.0001, output=0.0004 per 1k tokens
        cost, savings = _estimate_cost("google/gemini-2.0-flash-001", 1000, 1000)
        expected = (1000 / 1000) * 0.0001 + (1000 / 1000) * 0.0004
        assert abs(cost - expected) < 1e-8
        assert savings == 0.0  # No cache tokens → no savings

    def test_cost_estimation_unknown_model(self) -> None:
        from app.agent.channel.cost_tracker import _estimate_cost

        # Unknown model defaults to input=0.001, output=0.001 per 1k tokens
        cost, savings = _estimate_cost("unknown/model-xyz", 500, 200)
        expected = (500 / 1000) * 0.001 + (200 / 1000) * 0.001
        assert abs(cost - expected) < 1e-8

    def test_cost_estimation_with_cache(self) -> None:
        from app.agent.channel.cost_tracker import _estimate_cost

        # Claude Sonnet: input=0.003, cache_read=0.0003 per 1k
        # 1000 total input, 500 from cache read → 500 regular + 500 cached
        cost, savings = _estimate_cost("anthropic/claude-sonnet-4-6", 1000, 100, cache_read_tokens=500)
        assert savings > 0  # Should save money vs no cache
        assert cost < (1000 / 1000) * 0.003 + (100 / 1000) * 0.015  # Cheaper than full price

    def test_extract_usage_from_pydanticai_result(self) -> None:
        from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result

        # Mock PydanticAI result with usage()
        mock_usage = MagicMock()
        mock_usage.request_tokens = 200
        mock_usage.response_tokens = 100
        mock_usage.total_tokens = 300

        mock_result = MagicMock()
        mock_result.usage.return_value = mock_usage

        usage = extract_usage_from_pydanticai_result(mock_result, "google/gemini-2.0-flash-001", "screening")

        assert usage is not None
        assert usage.prompt_tokens == 200
        assert usage.completion_tokens == 100
        assert usage.total_tokens == 300
        assert usage.operation == "screening"

    def test_extract_usage_from_pydanticai_result_no_usage(self) -> None:
        from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result

        mock_result = MagicMock()
        mock_result.usage.return_value = None

        usage = extract_usage_from_pydanticai_result(mock_result, "some/model", "generation")
        assert usage is None

    async def test_log_usage_and_session_summary(self) -> None:
        from app.agent.channel.cost_tracker import LLMUsage, get_session_summary, log_usage

        await log_usage(
            LLMUsage(
                model="perplexity/sonar",
                operation="discovery",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                estimated_cost_usd=0.00015,
            )
        )
        await log_usage(
            LLMUsage(
                model="google/gemini-2.0-flash-001",
                operation="screening",
                prompt_tokens=200,
                completion_tokens=80,
                total_tokens=280,
                estimated_cost_usd=0.00005,
            )
        )
        await log_usage(
            LLMUsage(
                model="perplexity/sonar",
                operation="discovery",
                prompt_tokens=120,
                completion_tokens=60,
                total_tokens=180,
                estimated_cost_usd=0.00018,
            )
        )

        summary = get_session_summary()
        assert summary["total_tokens"] == 150 + 280 + 180
        assert summary["total_calls"] == 3
        assert summary["total_cost_usd"] > 0

        by_op = summary["by_operation"]
        assert "discovery" in by_op
        assert by_op["discovery"]["calls"] == 2
        assert by_op["discovery"]["tokens"] == 150 + 180

        assert "screening" in by_op
        assert by_op["screening"]["calls"] == 1
        assert by_op["screening"]["tokens"] == 280
