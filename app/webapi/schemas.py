"""Pydantic response schemas for the web UI API."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    title: str
    post_text: str
    status: str
    image_url: str | None
    image_urls: list[str] | None
    source_url: str | None
    scheduled_at: datetime.datetime | None
    published_at: datetime.datetime | None
    created_at: datetime.datetime


class PostDetail(PostRead):
    """Full post payload for the detail page — adds source_items blob."""

    external_id: str
    source_items: list[dict[str, Any]] | None = None


class ChannelRead(BaseModel):
    """List-page view of a channel — identifying + toggle fields only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    name: str
    description: str
    language: str
    enabled: bool
    max_posts_per_day: int
    critic_enabled: bool | None
    created_at: datetime.datetime


class ChannelSourceRead(BaseModel):
    """RSS source attached to a channel."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    source_type: str
    title: str | None
    language: str | None
    enabled: bool
    relevance_score: float
    error_count: int
    last_fetched_at: datetime.datetime | None
    last_error: str | None


class ChannelDetail(ChannelRead):
    """Full channel payload — adds config + sources + recent posts summary."""

    review_chat_id: int | None
    posting_schedule: list[str] | None
    publish_schedule: list[str] | None
    footer_template: str | None
    discovery_query: str
    modified_at: datetime.datetime
    sources: list[ChannelSourceRead]
    recent_posts: list[PostRead]


class DraftBucket(BaseModel):
    """Home tile: drafts grouped by channel."""

    channel_id: int
    channel_name: str
    count: int


class ScheduledPostEntry(BaseModel):
    """Home tile: scheduled post appearing in the next 24h window."""

    post_id: int
    channel_id: int
    channel_name: str
    title: str
    scheduled_at: datetime.datetime


class ModelCostBucket(BaseModel):
    """Per-model slice of the session cost summary."""

    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    calls: int


class SessionCostSummary(BaseModel):
    """In-memory cost aggregation from app.channel.cost_tracker.

    Resets whenever the bot restarts — this is a session view, not
    persistent history. Persistent storage is Phase 1.5 scope.
    """

    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_calls: int
    session_started_at: datetime.datetime
    by_model: list[ModelCostBucket]


class HomeStats(BaseModel):
    """Aggregated response backing the home dashboard's live tiles.

    Keeps home to one round-trip; skeleton tiles are FE-only and don't
    appear here.
    """

    drafts: list[DraftBucket]
    scheduled_next_24h: list[ScheduledPostEntry]
    session_cost: SessionCostSummary
