"""Unit tests for review image tools (business logic, no PydanticAI layer)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.review.image_tools import (
    ImageToolsDeps,
    add_image_url_op,
    clear_images_op,
    find_and_add_image_op,
    list_images_op,
    remove_image_op,
    reorder_images_op,
    use_candidate_op,
)
from app.core.enums import PostStatus
from app.db.models import ChannelPost

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker, *, pool: list[dict] | None = None, image_urls: list[str] | None = None) -> int:
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        p.image_urls = image_urls
        p.image_candidates = pool
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id


def _deps(post_id: int, session_maker) -> ImageToolsDeps:
    return ImageToolsDeps(
        session_maker=session_maker,
        post_id=post_id,
        channel_id=-100,
        api_key="k",
        vision_model="m",
        brave_api_key="",
    )


class TestListImages:
    async def test_empty(self, session_maker):
        pid = await _make_post(session_maker)
        out = await list_images_op(_deps(pid, session_maker))
        assert "no images" in out.lower() or "pool is empty" in out.lower()

    async def test_with_pool_and_selected(self, session_maker):
        pool = [
            {
                "url": "https://x/a.jpg",
                "source": "og_image",
                "quality_score": 8,
                "relevance_score": 7,
                "description": "a",
                "selected": True,
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
            },
            {
                "url": "https://x/b.jpg",
                "source": "brave_image",
                "quality_score": 6,
                "relevance_score": 6,
                "description": "b",
                "selected": False,
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
            },
        ]
        pid = await _make_post(session_maker, pool=pool, image_urls=["https://x/a.jpg"])
        out = await list_images_op(_deps(pid, session_maker))
        assert "a.jpg" in out
        assert "b.jpg" in out
        assert "selected" in out.lower() or "✓" in out


class TestUseCandidate:
    async def test_promotes_from_pool(self, session_maker):
        pool = [
            {
                "url": "https://x/a.jpg",
                "source": "og_image",
                "quality_score": 8,
                "selected": True,
                "relevance_score": 7,
                "description": "a",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
            },
            {
                "url": "https://x/b.jpg",
                "source": "brave_image",
                "quality_score": 7,
                "selected": False,
                "relevance_score": 7,
                "description": "b",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
            },
        ]
        pid = await _make_post(session_maker, pool=pool, image_urls=["https://x/a.jpg"])

        from sqlalchemy import select

        out = await use_candidate_op(_deps(pid, session_maker), pool_index=1)
        assert "b.jpg" in out
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/a.jpg", "https://x/b.jpg"]
        assert row.image_candidates[1]["selected"] is True

    async def test_invalid_pool_index(self, session_maker):
        pid = await _make_post(session_maker, pool=[], image_urls=[])
        out = await use_candidate_op(_deps(pid, session_maker), pool_index=5)
        assert "invalid" in out.lower() or "out of range" in out.lower()


class TestRemoveImage:
    async def test_removes_by_position(self, session_maker):
        pid = await _make_post(
            session_maker,
            image_urls=["https://x/a.jpg", "https://x/b.jpg"],
            pool=[
                {
                    "url": "https://x/a.jpg",
                    "source": "og_image",
                    "selected": True,
                    "quality_score": 8,
                    "relevance_score": 7,
                    "description": "a",
                    "is_logo": False,
                    "is_text_slide": False,
                    "is_duplicate": False,
                },
                {
                    "url": "https://x/b.jpg",
                    "source": "brave_image",
                    "selected": True,
                    "quality_score": 7,
                    "relevance_score": 7,
                    "description": "b",
                    "is_logo": False,
                    "is_text_slide": False,
                    "is_duplicate": False,
                },
            ],
        )

        from sqlalchemy import select

        await remove_image_op(_deps(pid, session_maker), position=0)
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/b.jpg"]
        assert row.image_candidates[0]["selected"] is False

    async def test_invalid_position(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["https://x/a.jpg"], pool=[])
        out = await remove_image_op(_deps(pid, session_maker), position=9)
        assert "invalid" in out.lower() or "out of range" in out.lower()


class TestReorderImages:
    async def test_swaps(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["a", "b", "c"], pool=[])

        from sqlalchemy import select

        await reorder_images_op(_deps(pid, session_maker), order=[2, 0, 1])
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["c", "a", "b"]

    async def test_invalid_length(self, session_maker):
        pid = await _make_post(session_maker, image_urls=["a", "b"], pool=[])
        out = await reorder_images_op(_deps(pid, session_maker), order=[0])
        assert "length" in out.lower() or "invalid" in out.lower()


class TestClearImages:
    async def test_clears(self, session_maker):
        pool = [
            {
                "url": "https://x/a.jpg",
                "source": "og_image",
                "selected": True,
                "quality_score": 8,
                "relevance_score": 7,
                "description": "a",
                "is_logo": False,
                "is_text_slide": False,
                "is_duplicate": False,
            }
        ]
        pid = await _make_post(session_maker, image_urls=["https://x/a.jpg"], pool=pool)
        from sqlalchemy import select

        await clear_images_op(_deps(pid, session_maker))
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == []
        assert row.image_candidates[0]["selected"] is False  # pool kept, just deselected


class TestAddImageUrl:
    async def test_adds_after_passing_filter(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])

        from app.channel.image_pipeline.filter import FilteredImage
        from app.channel.image_pipeline.score import ScoredImage
        from sqlalchemy import select

        from tests.fixtures.images import make_test_image

        data = make_test_image(width=900, height=700, colors=200, seed=1)
        filtered = [FilteredImage(url="https://x/new.jpg", width=900, height=700, bytes_=data)]
        scored = [
            ScoredImage(
                url="https://x/new.jpg",
                width=900,
                height=700,
                bytes_=data,
                quality_score=8,
                relevance_score=7,
                description="ok",
            )
        ]

        with (
            patch("app.channel.review.image_tools.cheap_filter", new=AsyncMock(return_value=filtered)),
            patch("app.channel.review.image_tools.vision_score", new=AsyncMock(return_value=scored)),
        ):
            out = await add_image_url_op(_deps(pid, session_maker), url="https://x/new.jpg")
        assert "added" in out.lower()

        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.image_urls == ["https://x/new.jpg"]
        assert row.image_candidates is not None
        assert len(row.image_candidates) == 1

    async def test_rejects_when_filter_drops(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])
        with patch("app.channel.review.image_tools.cheap_filter", new=AsyncMock(return_value=[])):
            out = await add_image_url_op(_deps(pid, session_maker), url="https://x/tiny.jpg")
        assert "rejected" in out.lower()


class TestFindAndAddImage:
    async def test_adds_top_search_result_to_pool(self, session_maker):
        pid = await _make_post(session_maker, image_urls=[], pool=[])

        from app.channel.image_pipeline.filter import FilteredImage
        from app.channel.image_pipeline.score import ScoredImage
        from sqlalchemy import select

        from tests.fixtures.images import make_test_image

        data = make_test_image(width=900, height=700, colors=200, seed=1)
        with (
            patch(
                "app.channel.review.image_tools.brave_image_search",
                new=AsyncMock(return_value=[{"url": "https://x/s.jpg"}]),
            ),
            patch(
                "app.channel.review.image_tools.cheap_filter",
                new=AsyncMock(return_value=[FilteredImage(url="https://x/s.jpg", width=900, height=700, bytes_=data)]),
            ),
            patch(
                "app.channel.review.image_tools.vision_score",
                new=AsyncMock(
                    return_value=[
                        ScoredImage(
                            url="https://x/s.jpg",
                            width=900,
                            height=700,
                            bytes_=data,
                            quality_score=8,
                            relevance_score=7,
                            description="photo",
                        )
                    ]
                ),
            ),
        ):
            out = await find_and_add_image_op(_deps(pid, session_maker), query="students in Prague")

        assert "s.jpg" in out
        async with session_maker() as session:
            row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        # Added to pool but NOT auto-selected.
        assert row.image_urls in (None, [])
        assert row.image_candidates is not None
        assert len(row.image_candidates) == 1
        assert row.image_candidates[0]["selected"] is False
