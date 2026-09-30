"""Retire the working languages nobody was matched on

Cutting the list in `db/seed.py` is enough for a database that gets seeded —
a fresh checkout, CI — and does nothing at all for production, where the
deploy runs `alembic upgrade head` and never the seed. So the retirement has
to happen here too, or the nine stay on the profile screen for ever.

Deactivated, not deleted. `users.spoken_langs` and `offers.langs` are plain
text arrays that reference nothing, so a deleted row leaves a profile claiming
a language with no name to show for it.

Revision ID: c3f1a80d47b2
Revises: a1c4e77b0d21
Create Date: 2026-07-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f1a80d47b2"
down_revision: str | Sequence[str] | None = "a1c4e77b0d21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The same four the interface speaks. Written out rather than imported from
# `seed.py`: a migration describes the database at one moment in time, and one
# that follows a constant would quietly change meaning the next time that
# constant did.
KEPT = ("ru", "uk", "cs", "en")
RETIRED = ("sk", "de", "kk", "uz", "vi")


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE languages SET is_active = false WHERE code NOT IN :kept").bindparams(
            sa.bindparam("kept", value=KEPT, expanding=True)
        )
    )


def downgrade() -> None:
    # The five this migration retired, and only those: anything else that is
    # inactive was made so by hand and is not ours to revive.
    op.execute(
        sa.text(
            "UPDATE languages SET is_active = true WHERE code IN :retired"
        ).bindparams(sa.bindparam("retired", value=RETIRED, expanding=True))
    )
