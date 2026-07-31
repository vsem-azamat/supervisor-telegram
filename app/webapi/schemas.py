"""Pydantic response schemas for the web UI API."""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ChatResourceStatus = Literal["discovered", "approved", "disabled"]


class PublicCatalogItem(BaseModel):
    """Safe public projection for the chat catalog."""

    resource_type: Literal["chat"]
    id: int
    title: str
    subtitle: str | None = None


class ChatRead(BaseModel):
    """List-page view of a managed chat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    resource_status: ChatResourceStatus
    is_forum: bool
    is_welcome_enabled: bool
    is_captcha_enabled: bool
    parent_chat_id: int | None = None
    relation_notes: str | None = None
    member_count: int | None = None  # enriched from Telethon, None when unavailable
    has_photo: bool = False
    last_synced_at: datetime.datetime | None = None
    created_at: datetime.datetime


class ChatUpdate(BaseModel):
    """Editable per-chat moderation settings. All fields optional — only the
    keys present in the body are applied (``exclude_unset``)."""

    title: str | None = None
    resource_status: ChatResourceStatus | None = None
    welcome_message: str | None = None
    is_welcome_enabled: bool | None = None
    is_captcha_enabled: bool | None = None
    time_delete: int | None = None
    parent_chat_id: int | None = None
    relation_notes: str | None = None


class ChatNode(BaseModel):
    """Recursive node for the /chats/graph tree response.

    member_count is intentionally NOT enriched here — the tree endpoint
    skips Telethon to avoid N+1 RPCs on every poll. Drill into /chats/:id
    for live counts.
    """

    id: int
    title: str | None
    relation_notes: str | None = None
    has_photo: bool = False
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


class ChatSender(BaseModel):
    """Recent sender in a chat — used for moderation actions."""

    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    message_count: int
    last_seen: datetime.datetime
    blocked: bool


class ChatDetail(ChatRead):
    """Full chat payload — adds heatmap grid + member-snapshot series + relationships."""

    welcome_message: str | None
    time_delete: int
    modified_at: datetime.datetime
    heatmap: list[HeatmapCell]
    member_snapshots: list[MemberSnapshotPoint]
    children: list[ChatNode] = []
    spam_pings: list[SpamPingRead] = []
    recent_senders: list[ChatSender] = []


class UserBlockRequest(BaseModel):
    """Body for POST /api/users/{id}/block. Set ``revoke_messages`` to also
    delete the user's recorded messages from all known chats."""

    revoke_messages: bool = False


class UserBlockResponse(BaseModel):
    user_id: int
    blocked: bool
    message: str


class AdminSessionRead(BaseModel):
    """Active admin session row — used by /settings to list logins."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    user_id: int
    created_at: datetime.datetime
    last_seen_at: datetime.datetime
    expires_at: datetime.datetime
    user_agent: str | None
    ip: str | None
    is_current: bool = False


class FeatureFlagRead(BaseModel):
    """One feature flag — surfaced as a badge in /settings."""

    name: str
    enabled: bool
    source: str = "env"


class SystemStatus(BaseModel):
    """Read-only operational status for the /settings system card."""

    super_admin_ids: list[int]
    telethon_connected: bool
    publish_bot_ready: bool
    allowed_origins: list[str]
    session_ttl_days: int
    feature_flags: list[FeatureFlagRead]


ChatNode.model_rebuild()


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


class HomeStats(BaseModel):
    """Aggregated response backing the home dashboard's live tiles.

    Keeps home to one round-trip; skeleton tiles are FE-only and don't
    appear here.
    """

    chat_heatmap: list[ChatHeatmapSummary] = []
    members_delta: list[MembersDeltaEntry] = []
    spam_pings: SpamPingsSummary = SpamPingsSummary(count_24h=0, count_7d=0, recent=[])


class TelegramLoginPayload(BaseModel):
    """Payload POSTed by the Telegram Login Widget. Extra keys are preserved so HMAC verifies."""

    model_config = ConfigDict(extra="allow")

    id: int
    auth_date: int
    hash: str


class MagicLinkLoginPayload(BaseModel):
    token: str


class AuthMeResponse(BaseModel):
    user_id: int
    auth_mode: str = "telegram"
    is_authenticated: bool = True
