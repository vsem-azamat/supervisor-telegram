"""E2E: admin edits images via the review agent.

Exercises the full agent → image_tools → DB → Telegram-refresh round trip
against the FakeTelegramServer and an in-memory SQLite DB.

The test stubs the LLM layer (PydanticAI agent.run) so no real API calls are
made.  The key assertion is that ``image_urls`` in the DB reflects the
``use_candidate_op`` invocation the stub fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from app.channel.review.agent import ReviewAgentDeps, review_agent_turn
from app.channel.review.image_tools import ImageToolsDeps, use_candidate_op
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.fake_telegram import FakeTelegramServer

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_CHAT_ID = -1001
CHANNEL_ID = -100

# ---------------------------------------------------------------------------
# Local bot fixture (same pattern as test_channel_review.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def bot(fake_tg: FakeTelegramServer) -> Bot:
    """Bot connected to the FakeTelegramServer."""
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


# ---------------------------------------------------------------------------
# Helper: seed a post with an image pool
# ---------------------------------------------------------------------------


async def _seed_post_with_pool(session_maker: async_sessionmaker[AsyncSession]) -> int:
    """Insert a draft ChannelPost with two image candidates, return its ID."""
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=CHANNEL_ID,
            external_id="e1",
            title="Students news",
            post_text="Body text.\n\n——",
            status=PostStatus.DRAFT,
        )
        post.image_urls = ["https://x/a.jpg"]
        post.image_url = "https://x/a.jpg"
        post.image_candidates = [
            {
                "url": "https://x/a.jpg",
                "source": "og_image",
                "quality_score": 7,
                "relevance_score": 6,
                "description": "main photo",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
                "selected": True,
            },
            {
                "url": "https://x/b.jpg",
                "source": "article_body",
                "quality_score": 8,
                "relevance_score": 8,
                "description": "second photo",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
                "selected": False,
            },
        ]
        post.review_message_id = 5555
        post.review_chat_id = REVIEW_CHAT_ID
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_use_candidate_op_promotes_second_image(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Direct call to use_candidate_op promotes pool[1] to position 0 in image_urls.

    This is the core DB-state assertion: no agent or Telegram involvement.
    """
    post_id = await _seed_post_with_pool(db_session_maker)

    tool_deps = ImageToolsDeps(
        session_maker=db_session_maker,
        post_id=post_id,
        channel_id=CHANNEL_ID,
        api_key="k",
        vision_model="m",
        brave_api_key="",
    )

    result = await use_candidate_op(tool_deps, pool_index=1, position=0)

    assert "b.jpg" in result, f"Unexpected result: {result}"

    async with db_session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()

    # b.jpg was inserted at position 0, a.jpg stays at position 1
    assert row.image_urls == ["https://x/b.jpg", "https://x/a.jpg"]


@pytest.mark.e2e
async def test_admin_uses_second_candidate_via_agent_stub(
    bot: Bot,
    fake_tg: FakeTelegramServer,
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Stub the LLM; agent turn executes use_candidate_op → DB updated correctly."""
    post_id = await _seed_post_with_pool(db_session_maker)

    deps = ReviewAgentDeps(
        session_maker=db_session_maker,
        bot=bot,
        post_id=post_id,
        channel_id=CHANNEL_ID,
        channel_name="Konnekt",
        channel_username="konnekt_channel",
        footer="——\n🔗 **Konnekt**",
        review_chat_id=REVIEW_CHAT_ID,
    )

    # Stub create_review_agent so no real OpenRouter call is made.
    # The fake agent.run directly invokes use_candidate_op via the real image_tools module.
    with patch("app.channel.review.agent.create_review_agent") as mock_factory:

        class _FakeResult:
            output = "Использовал кандидата 1 и поставил его первым."

            def all_messages(self) -> list:
                return []

            def new_messages(self) -> list:
                return []

        async def _fake_run(prompt: str, deps: ReviewAgentDeps, message_history=None):  # noqa: ANN001
            tool_deps = ImageToolsDeps(
                session_maker=deps.session_maker,
                post_id=deps.post_id,
                channel_id=deps.channel_id,
                api_key="k",
                vision_model="m",
                brave_api_key="",
            )
            await use_candidate_op(tool_deps, pool_index=1, position=0)
            return _FakeResult()

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=_fake_run)
        mock_factory.return_value = mock_agent

        response = await review_agent_turn(
            post_id=post_id,
            user_message="покажи фотки; возьми вторую и поставь первой",
            deps=deps,
        )

    assert response  # agent returned something

    async with db_session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()

    assert row.image_urls == ["https://x/b.jpg", "https://x/a.jpg"]
