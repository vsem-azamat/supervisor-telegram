"""Pydantic response schemas for the web UI API."""

from __future__ import annotations

import datetime

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
