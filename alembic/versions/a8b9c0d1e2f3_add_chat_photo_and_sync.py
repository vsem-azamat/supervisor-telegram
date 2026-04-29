"""Add chat photo_file_id + last_synced_at columns.

Decouples Telethon-driven syncs from admin-driven edits:
* ``photo_file_id`` caches the Bot API ``photo.big_file_id`` (or Telethon
  ``photo_id`` fallback) so the UI can render avatars without re-querying
  Telegram on every page load.
* ``last_synced_at`` records the timestamp of the most recent metadata
  pull from Telegram. Until now the snapshot loop's staleness check
  piggy-backed on ``modified_at``, which also bumps when admins edit a
  row from the web UI — so an admin save would suppress the next 24h of
  Telegram refreshes. ``last_synced_at`` records sync-time only; admin
  writes leave it alone.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-04-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("photo_file_id", sa.String(), nullable=True))
    op.add_column("chats", sa.Column("last_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "last_synced_at")
    op.drop_column("chats", "photo_file_id")
