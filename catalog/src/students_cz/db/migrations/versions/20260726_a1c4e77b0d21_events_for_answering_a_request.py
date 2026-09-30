"""answering a request: price unit and two events

Revision ID: a1c4e77b0d21
Revises: fbdbb4c11417
Create Date: 2026-07-26 16:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c4e77b0d21"
down_revision: Union[str, Sequence[str], None] = "fbdbb4c11417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Two new members of the native enum. IF NOT EXISTS because a database
# stamped from metadata rather than migrated already has them, and this
# migration must not be the thing that breaks that database.
NEW_VALUES = ("request_responded", "response_accepted")


def upgrade() -> None:
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE user_event_kind ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "request_responses",
        sa.Column(
            "price_unit",
            # The type already exists — offers use it — so create_type=False,
            # or this fails with "type price_unit already exists".
            postgresql.ENUM(name="price_unit", create_type=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drops the column only.

    Postgres cannot drop a value from an enum. Recreating the type would mean
    rewriting every column that uses it and losing the rows that hold the value
    being removed — a far worse outcome than an enum with two unused members.
    """
    op.drop_column("request_responses", "price_unit")
