"""End-to-end tests for channel post review flow.

Uses:
- FakeTelegramServer to simulate Telegram Bot API
- SQLite in-memory for DB (fast, no docker needed)
- Direct calls to review.py functions (send_for_review, handle_approve, handle_reject)
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from app.agent.channel.review import (
    handle_approve,
    handle_reject,
    send_for_review,
)
from app.agent.channel.sources import ContentItem
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import ChannelPost, ChannelSource
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tests.fake_telegram import FakeTelegramServer

# ---- Constants ----

REVIEW_CHAT_ID = -1001111111111
CHANNEL_ID = "@test_channel"
CHANNEL_CHAT_ID = -1002222222222


def _make_content_item(
    title: str = "Czech visa update",
    body: str = "New rules for student visas in 2026.",
    url: str = "https://example.com/article-1",
    source_url: str = "https://example.com/feed.xml",
) -> ContentItem:
    return ContentItem(
        source_url=source_url,
        external_id="test-ext-1",
        title=title,
        body=body,
        url=url,
    )


class _FakeGeneratedPost:
    """Mimics GeneratedPost (pydantic model) with a text attribute."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.is_sensitive = False
        self.image_url = None


# ---- Fixtures ----


@pytest_asyncio.fixture()
async def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session_maker(db_engine: AsyncEngine):
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture()
async def fake_tg():
    """Start fake Telegram server."""
    async with FakeTelegramServer() as server:
        yield server


@pytest_asyncio.fixture()
async def bot(fake_tg: FakeTelegramServer):
    """Bot connected to fake Telegram server."""
    from aiogram.client.telegram import TelegramAPIServer

    api_server = TelegramAPIServer(
        base=f"{fake_tg.base_url}/bot{{token}}/{{method}}",
        file=f"{fake_tg.base_url}/file/bot{{token}}/{{path}}",
        is_local=True,
    )
    session = AiohttpSession(api=api_server)
    b = Bot(
        token="123456:ABC-DEF1234567890",
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    yield b
    await b.session.close()


# ---- Helper to seed a draft post ----


async def _seed_draft_post(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    source_items: list[dict[str, str]] | None = None,
    post_text: str = "<b>Czech visa update</b>\n\nNew rules for student visas.",
    review_message_id: int | None = 500,
) -> int:
    """Insert a draft ChannelPost and return its ID."""
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=CHANNEL_ID,
            external_id="seed-ext-1",
            title="Czech visa update",
            post_text=post_text,
            source_items=source_items,
            review_message_id=review_message_id,
            review_chat_id=REVIEW_CHAT_ID,
        )
        session.add(post)
        await session.flush()
        post_id = post.id
        await session.commit()
    return post_id


async def _seed_channel_source(
    session_maker: async_sessionmaker[AsyncSession],
    url: str = "https://example.com/feed.xml",
    relevance_score: float = 1.0,
) -> int:
    """Insert a ChannelSource and return its ID."""
    async with session_maker() as session:
        source = ChannelSource(
            channel_id=CHANNEL_ID,
            url=url,
            title="Example Feed",
        )
        source.relevance_score = relevance_score
        session.add(source)
        await session.flush()
        source_id = source.id
        await session.commit()
    return source_id


# ---- Tests ----


@pytest.mark.e2e
class TestSendForReview:
    """Tests for the send_for_review function."""

    async def test_send_for_review_creates_post_and_sends_message(
        self,
        bot: Bot,
        fake_tg: FakeTelegramServer,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """send_for_review should create a draft post in DB and send a message with inline keyboard."""
        post = _FakeGeneratedPost(text="<b>Big news</b>\n\nNew student housing rules in Prague.")
        items = [_make_content_item()]

        post_id = await send_for_review(
            bot=bot,
            review_chat_id=REVIEW_CHAT_ID,
            channel_id=CHANNEL_ID,
            post=post,  # type: ignore[arg-type]
            source_items=items,
            session_maker=db_session_maker,
        )

        # Should return a valid post ID
        assert post_id is not None

        # DB should have a draft post with review_message_id set
        async with db_session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            db_post = result.scalar_one()
            assert db_post.status == "draft"
            assert db_post.review_message_id is not None
            assert db_post.channel_id == CHANNEL_ID
            assert "Big news" in db_post.post_text

        # FakeTelegramServer should have received a sendMessage call
        send_calls = fake_tg.get_calls("sendMessage")
        assert len(send_calls) >= 1
        last_send = send_calls[-1]
        assert str(REVIEW_CHAT_ID) == str(last_send.params.get("chat_id"))
        # Should have inline keyboard (reply_markup)
        assert "reply_markup" in last_send.params


@pytest.mark.e2e
class TestHandleApprove:
    """Tests for handle_approve."""

    async def test_approve_publishes_to_channel(
        self,
        bot: Bot,
        fake_tg: FakeTelegramServer,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Approving a draft should send the post to the channel and update DB status."""
        post_id = await _seed_draft_post(db_session_maker)

        result = await handle_approve(
            bot=bot,
            post_id=post_id,
            channel_id=CHANNEL_CHAT_ID,
            session_maker=db_session_maker,
        )

        assert "Published" in result

        # DB should show approved with telegram_message_id
        async with db_session_maker() as session:
            stmt = select(ChannelPost).where(ChannelPost.id == post_id)
            db_post = (await session.execute(stmt)).scalar_one()
            assert db_post.status == "approved"
            assert db_post.telegram_message_id is not None

        # FakeTelegramServer received sendMessage to the channel
        send_calls = fake_tg.get_calls("sendMessage")
        channel_sends = [c for c in send_calls if str(c.params.get("chat_id")) == str(CHANNEL_CHAT_ID)]
        assert len(channel_sends) >= 1

    async def test_approve_already_published(
        self,
        bot: Bot,
        fake_tg: FakeTelegramServer,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Approving an already-approved post should return 'Already published'."""
        post_id = await _seed_draft_post(db_session_maker)

        # Approve once
        await handle_approve(bot=bot, post_id=post_id, channel_id=CHANNEL_CHAT_ID, session_maker=db_session_maker)

        # Approve again
        result = await handle_approve(
            bot=bot, post_id=post_id, channel_id=CHANNEL_CHAT_ID, session_maker=db_session_maker
        )
        assert "Already published" in result


@pytest.mark.e2e
class TestHandleReject:
    """Tests for handle_reject."""

    async def test_reject_updates_status(
        self,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Rejecting a draft should set status to 'rejected' and store feedback."""
        post_id = await _seed_draft_post(db_session_maker)

        result = await handle_reject(
            post_id=post_id,
            session_maker=db_session_maker,
            reason="Off topic",
        )

        assert "rejected" in result.lower()

        async with db_session_maker() as session:
            stmt = select(ChannelPost).where(ChannelPost.id == post_id)
            db_post = (await session.execute(stmt)).scalar_one()
            assert db_post.status == "rejected"
            assert db_post.admin_feedback == "Off topic"

    async def test_reject_without_reason(
        self,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Rejecting without a reason should still update status."""
        post_id = await _seed_draft_post(db_session_maker)

        result = await handle_reject(post_id=post_id, session_maker=db_session_maker)

        assert "rejected" in result.lower()

        async with db_session_maker() as session:
            stmt = select(ChannelPost).where(ChannelPost.id == post_id)
            db_post = (await session.execute(stmt)).scalar_one()
            assert db_post.status == "rejected"
            assert db_post.admin_feedback is None


@pytest.mark.e2e
class TestSourceRelevance:
    """Tests for source relevance updates on approve/reject."""

    async def test_approve_updates_source_relevance(
        self,
        bot: Bot,
        fake_tg: FakeTelegramServer,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Approving a post should boost the relevance score of contributing sources."""
        source_url = "https://example.com/feed-approve.xml"
        source_id = await _seed_channel_source(db_session_maker, url=source_url, relevance_score=1.0)

        post_id = await _seed_draft_post(
            db_session_maker,
            source_items=[
                {"title": "Article", "url": "https://example.com/a1", "source_url": source_url},
            ],
        )

        await handle_approve(
            bot=bot,
            post_id=post_id,
            channel_id=CHANNEL_CHAT_ID,
            session_maker=db_session_maker,
        )

        # Source relevance should have increased (boost_relevance adds 0.1)
        async with db_session_maker() as session:
            stmt = select(ChannelSource).where(ChannelSource.id == source_id)
            source = (await session.execute(stmt)).scalar_one()
            assert source.relevance_score > 1.0

    async def test_reject_penalizes_source_relevance(
        self,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Rejecting a post should decrease the relevance score of contributing sources."""
        source_url = "https://example.com/feed-reject.xml"
        source_id = await _seed_channel_source(db_session_maker, url=source_url, relevance_score=1.0)

        post_id = await _seed_draft_post(
            db_session_maker,
            source_items=[
                {"title": "Article", "url": "https://example.com/a2", "source_url": source_url},
            ],
        )

        await handle_reject(post_id=post_id, session_maker=db_session_maker, reason="Irrelevant")

        # Source relevance should have decreased (penalize_relevance subtracts 0.2)
        async with db_session_maker() as session:
            stmt = select(ChannelSource).where(ChannelSource.id == source_id)
            source = (await session.execute(stmt)).scalar_one()
            assert source.relevance_score < 1.0


@pytest.mark.e2e
class TestFullFlow:
    """Full end-to-end review flow tests."""

    async def test_full_flow_review_to_publish(
        self,
        bot: Bot,
        fake_tg: FakeTelegramServer,
        db_session_maker: async_sessionmaker[AsyncSession],
    ):
        """Full chain: create sources, send_for_review, then approve -- verify everything."""
        # Step 1: Create a source in DB
        source_url = "https://example.com/full-flow-feed.xml"
        source_id = await _seed_channel_source(db_session_maker, url=source_url, relevance_score=1.0)

        # Step 2: Send for review
        post = _FakeGeneratedPost(text="<b>Full flow test</b>\n\nNew scholarship for 2026.")
        items = [
            _make_content_item(
                title="Scholarship news",
                body="New scholarships available for CIS students.",
                url="https://example.com/scholarship",
                source_url=source_url,
            ),
        ]

        post_id = await send_for_review(
            bot=bot,
            review_chat_id=REVIEW_CHAT_ID,
            channel_id=CHANNEL_ID,
            post=post,  # type: ignore[arg-type]
            source_items=items,
            session_maker=db_session_maker,
        )
        assert post_id is not None

        # Verify draft was created
        async with db_session_maker() as session:
            stmt = select(ChannelPost).where(ChannelPost.id == post_id)
            db_post = (await session.execute(stmt)).scalar_one()
            assert db_post.status == "draft"
            assert db_post.review_message_id is not None

        # Verify review message was sent
        review_sends = fake_tg.get_calls("sendMessage")
        assert len(review_sends) >= 1

        # Step 3: Approve the post
        fake_tg.reset()  # Clear previous calls to isolate the approve step

        result = await handle_approve(
            bot=bot,
            post_id=post_id,
            channel_id=CHANNEL_CHAT_ID,
            session_maker=db_session_maker,
        )
        assert "Published" in result

        # Verify post is approved in DB
        async with db_session_maker() as session:
            stmt = select(ChannelPost).where(ChannelPost.id == post_id)
            db_post = (await session.execute(stmt)).scalar_one()
            assert db_post.status == "approved"
            assert db_post.telegram_message_id is not None

        # Verify message was sent to the channel
        publish_sends = fake_tg.get_calls("sendMessage")
        channel_sends = [c for c in publish_sends if str(c.params.get("chat_id")) == str(CHANNEL_CHAT_ID)]
        assert len(channel_sends) == 1

        # Verify source relevance was boosted
        async with db_session_maker() as session:
            src_stmt = select(ChannelSource).where(ChannelSource.id == source_id)
            source = (await session.execute(src_stmt)).scalar_one()
            assert source.relevance_score > 1.0
