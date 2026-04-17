"""Tests that workflow.generate_post resolves and passes critic flags."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.workflow import generate_post as wf_generate

pytestmark = pytest.mark.asyncio


class _Channel(SimpleNamespace):
    pass


async def _make_state():
    channel = _Channel(
        id=1,
        telegram_id=-100,
        name="X",
        language="ru",
        footer="——\n🔗 **Konnekt** | @konnekt_channel",
        footer_template=None,
        username="konnekt_channel",
        discovery_query="",
        critic_enabled=True,  # per-channel override
    )
    config = SimpleNamespace(
        generation_model="gen-model",
        vision_model="vis-model",
        image_phash_threshold=10,
        image_phash_lookback_posts=30,
        screening_model="sc",
        http_timeout=30,
        temperature=0.3,
        embedding_model="emb",
        semantic_dedup_threshold=0.9,
        dedup_lookback_days=30,
        dedup_query_snippet_chars=200,
        critic_enabled=False,  # global — ignored because channel is True
        critic_model="anthropic/claude-sonnet-4-6",
    )

    return {
        "relevant_items": [
            SimpleNamespace(title="T", body="B", url="https://x/1", source_url="https://rss", external_id="e")
        ],
        "api_key": "k",
        "config": config,
        "channel": channel,
        "channel_id": 1,
        "session_maker": AsyncMock(),
    }


class _State:
    """Simple dict-backed stand-in for Burr's State object."""

    def __init__(self, data: dict | None = None) -> None:
        self._data: dict = dict(data) if data else {}

    def __getitem__(self, key: str):  # noqa: ANN001
        return self._data[key]

    def __setitem__(self, key: str, value) -> None:  # noqa: ANN001
        self._data[key] = value

    def update(self, **kw):  # noqa: ANN002
        new = _State(self._data)
        for k, v in kw.items():
            new._data[k] = v
        return new


async def test_workflow_generate_passes_critic_flags():
    state = await _make_state()
    s = _State(state)

    captured: dict = {}

    async def fake_generate(items, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="🎓 **H**\n\nB [l](https://x/1)\n\n" + state["channel"].footer,
            pre_critic_text=None,
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
            model_dump=lambda: {"text": "x"},
        )

    async def fake_find_nearest_posts(*args, **kwargs):
        return []

    async def fake_feedback(**kwargs):
        return None

    with (
        patch("app.channel.generator.generate_post", new=fake_generate),
        patch("app.channel.semantic_dedup.find_nearest_posts", new=fake_find_nearest_posts),
        patch("app.channel.feedback.get_feedback_summary", new=fake_feedback),
    ):
        await wf_generate(s)

    assert captured["critic_enabled"] is True
    assert captured["critic_model"] == "anthropic/claude-sonnet-4-6"


async def test_workflow_generate_channel_none_uses_global():
    state = await _make_state()
    state["channel"].critic_enabled = None  # fall back to global
    state["config"].critic_enabled = True

    s = _State(state)

    captured: dict = {}

    async def fake_generate(items, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="🎓 **H**\n\n\n\n" + state["channel"].footer,
            pre_critic_text=None,
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
            model_dump=lambda: {"text": "x"},
        )

    async def fake_find(*args, **kwargs):
        return []

    async def fake_feedback(**kwargs):
        return None

    with (
        patch("app.channel.generator.generate_post", new=fake_generate),
        patch("app.channel.semantic_dedup.find_nearest_posts", new=fake_find),
        patch("app.channel.feedback.get_feedback_summary", new=fake_feedback),
    ):
        await wf_generate(s)

    assert captured["critic_enabled"] is True


async def test_create_review_post_persists_pre_critic_text(session_maker):
    from app.channel.generator import GeneratedPost
    from app.channel.review.service import create_review_post
    from app.channel.sources import ContentItem
    from app.db.models import ChannelPost
    from sqlalchemy import select

    post = GeneratedPost(
        text="🎓 **H**\n\nB [l](https://x/1)\n\n——\n🔗 **K** | @c",
        pre_critic_text="🎓 **Original**\n\nOrig body\n\n——\n🔗 **K** | @c",
    )
    item = ContentItem(
        source_url="https://rss",
        external_id="e1",
        title="T",
        body="B",
        url="https://x/1",
    )
    async with session_maker() as session:
        cp = await create_review_post(
            channel_id=-100,
            post=post,
            source_items=[item],
            review_chat_id=-200,
            session=session,
        )
        await session.commit()
    assert cp is not None
    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == cp.id))).scalar_one()
    assert row.pre_critic_text.startswith("🎓 **Original**")


async def test_regen_post_text_threads_critic_and_persists(session_maker, monkeypatch):
    """regen_post_text must pass critic flags to generate_post and save pre_critic_text."""
    from app.channel.review.service import regen_post_text
    from app.core.enums import PostStatus
    from app.db.models import Channel, ChannelPost

    async with session_maker() as session:
        ch = Channel(
            telegram_id=-100,
            name="X",
            username="konnekt_channel",
            footer_template="——\n🔗 **K** | @c",
            critic_enabled=True,
        )
        session.add(ch)
        await session.flush()
        p = ChannelPost(
            channel_id=ch.telegram_id,
            external_id="e",
            title="t",
            post_text="old",
            status=PostStatus.DRAFT,
            source_items=[{"title": "T", "url": "https://x/1", "source_url": "https://rss", "external_id": "e"}],
        )
        session.add(p)
        await session.commit()
        pid = p.id

    captured_kwargs: dict = {}

    async def fake_generate(items, **kwargs):
        from types import SimpleNamespace

        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            text="🎓 **New**\n\nBody [l](https://x/1)\n\n——\n🔗 **K** | @c",
            pre_critic_text="🎓 **Original**\n\nBody [l](https://x/1)\n\n——\n🔗 **K** | @c",
            image_urls=[],
            image_url=None,
            image_candidates=None,
            image_phashes=[],
        )

    # The regen path uses `from app.channel.generator import generate_post`
    # (local import inside regen_post_text). Patch at the module source so the
    # subsequent local import binds to the fake.
    monkeypatch.setattr("app.channel.generator.generate_post", fake_generate)

    msg, post = await regen_post_text(
        session_maker=session_maker,
        post_id=pid,
        api_key="k",
        model="gen-m",
        language="Russian",
        footer="——\n🔗 **K** | @c",
    )
    assert post is not None
    assert captured_kwargs.get("critic_enabled") is True
    assert captured_kwargs.get("critic_model") == "anthropic/claude-sonnet-4-6"

    from sqlalchemy import select

    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
    assert row.pre_critic_text.startswith("🎓 **Original**")
