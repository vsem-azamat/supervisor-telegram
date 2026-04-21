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


class ChatRead(BaseModel):
    """List-page view of a managed chat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    is_forum: bool
    is_welcome_enabled: bool
    is_captcha_enabled: bool
    parent_chat_id: int | None = None
    relation_notes: str | None = None
    member_count: int | None = None  # enriched from Telethon, None when unavailable
    created_at: datetime.datetime


class ChatNode(BaseModel):
    """Recursive node for the /chats/graph tree response.

    member_count is intentionally NOT enriched here — the tree endpoint
    skips Telethon to avoid N+1 RPCs on every poll. Drill into /chats/:id
    for live counts.
    """

    id: int
    title: str | None
    relation_notes: str | None = None
    children: list[ChatNode] = []


class HeatmapCell(BaseModel):
    """One cell of the weekday×hour chat activity grid.

    weekday: 0 = Monday, 6 = Sunday (matches datetime.weekday()).
    hour: 0..23, UTC.
    count: number of messages recorded in `messages` table for that cell
           over the lookback window.
    """

    weekday: int
    hour: int
    count: int


class MemberSnapshotPoint(BaseModel):
    captured_at: datetime.datetime
    member_count: int


class ChatDetail(ChatRead):
    """Full chat payload — adds heatmap grid + member-snapshot series + relationships."""

    welcome_message: str | None
    time_delete: int
    modified_at: datetime.datetime
    heatmap: list[HeatmapCell]
    member_snapshots: list[MemberSnapshotPoint]
    children: list[ChatNode] = []
    spam_pings: list[SpamPingRead] = []


ChatNode.model_rebuild()


class PostViewsEntry(BaseModel):
    """Home tile: post view counts for the last N published posts."""

    post_id: int
    channel_id: int
    channel_name: str
    title: str
    published_at: datetime.datetime
    views: int


class ChatHeatmapSummary(BaseModel):
    """Home tile: per-chat total activity over the last 7 days.

    We send totals (not the full grid) to keep the home payload small;
    the full grid lives on /chats/:id.
    """

    chat_id: int
    title: str | None
    total_messages: int


class MembersDeltaEntry(BaseModel):
    """Home tile: members Δ over a window.

    delta_24h / delta_7d: None when no baseline snapshot exists yet
    (first run, or snapshot history too short).
    """

    chat_id: int
    title: str | None
    current: int | None
    delta_24h: int | None
    delta_7d: int | None


class DraftBucket(BaseModel):
    """Home tile: drafts grouped by channel."""

    channel_id: int
    channel_name: str
    count: int


class SpamPingRead(BaseModel):
    """One ad-detection event surfaced to the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    chat_title: str | None = None
    user_id: int
    message_id: int
    kind: str
    matches: list[str]
    snippet: str | None
    detected_at: datetime.datetime


class SpamPingsSummary(BaseModel):
    """Home tile: rolling spam-ping counters + recent samples."""

    count_24h: int
    count_7d: int
    recent: list[SpamPingRead] = []


class ScheduledPostEntry(BaseModel):
    """Home tile: scheduled post appearing in the next 24h window."""

    post_id: int
    channel_id: int
    channel_name: str
    title: str
    scheduled_at: datetime.datetime


class OperationCostBucket(BaseModel):
    """Per-operation slice of the session cost summary.

    Operation is the pipeline phase (screening, generation, discovery,
    feedback, edit, source_discovery) — that's how cost_tracker groups
    usage internally.
    """

    operation: str
    tokens: int
    cost_usd: float
    calls: int
    cache_savings_usd: float


class SessionCostSummary(BaseModel):
    """In-memory cost aggregation from app.channel.cost_tracker.

    Resets whenever the bot restarts — this is a session view, not
    persistent history. Persistent storage is Phase 1.5 scope.
    """

    total_tokens: int
    total_cost_usd: float
    total_calls: int
    cache_read_tokens: int
    cache_write_tokens: int
    cache_savings_usd: float
    by_operation: list[OperationCostBucket]

    @classmethod
    def from_tracker(cls, summary: dict[str, Any]) -> SessionCostSummary:
        """Adapt `cost_tracker.get_session_summary()` output into a response.

        Keeping the shape-conversion in one place prevents the /costs and
        /stats/home endpoints from drifting apart as cost_tracker evolves.
        """
        buckets = [
            OperationCostBucket(
                operation=op_name,
                tokens=int(data.get("tokens", 0)),
                cost_usd=float(data.get("cost_usd", 0.0)),
                calls=int(data.get("calls", 0)),
                cache_savings_usd=float(data.get("cache_savings_usd", 0.0)),
            )
            for op_name, data in (summary.get("by_operation") or {}).items()
        ]
        return cls(
            total_tokens=int(summary.get("total_tokens", 0)),
            total_cost_usd=float(summary.get("total_cost_usd", 0.0)),
            total_calls=int(summary.get("total_calls", 0)),
            cache_read_tokens=int(summary.get("cache_read_tokens", 0)),
            cache_write_tokens=int(summary.get("cache_write_tokens", 0)),
            cache_savings_usd=float(summary.get("cache_savings_usd", 0.0)),
            by_operation=buckets,
        )


class AgentMessage(BaseModel):
    """One row in the chat-UI projection of the agent conversation."""

    role: str  # "user" | "assistant" | "tool"
    text: str | None = None
    tool_name: str | None = None
    tool_label: str | None = None
    result_preview: str | None = None


class AgentHistory(BaseModel):
    """Persisted-conversation snapshot for /agent."""

    user_id: int
    message_count: int
    messages: list[AgentMessage]


class AgentTurnRequest(BaseModel):
    """Body of POST /api/agent/turn."""

    message: str


class HomeStats(BaseModel):
    """Aggregated response backing the home dashboard's live tiles.

    Keeps home to one round-trip; skeleton tiles are FE-only and don't
    appear here.
    """

    drafts: list[DraftBucket]
    scheduled_next_24h: list[ScheduledPostEntry]
    session_cost: SessionCostSummary
    post_views: list[PostViewsEntry] = []
    chat_heatmap: list[ChatHeatmapSummary] = []
    members_delta: list[MembersDeltaEntry] = []
    spam_pings: SpamPingsSummary = SpamPingsSummary(count_24h=0, count_7d=0, recent=[])
