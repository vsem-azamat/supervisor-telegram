"""Give every service type the shape of the form that offers it

The column alone would leave all twelve on the `lesson` default, which is the
form they already get — so this migration is the values, not the column. Written
out here rather than imported from `db/seed.py` for the reason the grouping
migration gives: the deploy runs `alembic upgrade head` and never the seed, so a
shape that exists only in the seed reaches every developer's database and no
production one. `tests/test_service_groups.py` fails when the two disagree.

Revision ID: 5b2a9c41e7d3
Revises: 146127771c2c
Create Date: 2026-07-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b2a9c41e7d3"
down_revision: str | Sequence[str] | None = "146127771c2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FORMS = ("lesson", "work", "errand")

# Every service type and the form it is offered through. A constant of its own
# rather than a reference to the seed: a migration describes the database at one
# moment, and one that follows a constant changes meaning the next time that
# constant does.
SERVICE_TYPES: list[dict] = [
    {"code": "tutoring", "form": "lesson"},
    {"code": "language_tutoring", "form": "lesson"},
    {"code": "exam_prep", "form": "lesson"},
    {"code": "entrance_prep", "form": "lesson"},
    {"code": "writing", "form": "work"},
    # Not a lesson. It sits on the entrance shelf, where a student compares it
    # with exam preparation, but what it asks the person offering it has nothing
    # to do with teaching: it is standby for one event on one day.
    {"code": "exam_live_help", "form": "errand"},
    {"code": "nostrification", "form": "errand"},
    {"code": "insurance", "form": "errand"},
    {"code": "bank_letter", "form": "errand"},
    {"code": "translation", "form": "errand"},
    {"code": "residence", "form": "errand"},
    {"code": "housing", "form": "errand"},
]


def upgrade() -> None:
    bind = op.get_bind()

    sa.Enum(*FORMS, name="service_form").create(bind, checkfirst=True)
    op.add_column(
        "service_types",
        sa.Column(
            "form_shape",
            sa.Enum(*FORMS, name="service_form", create_type=False),
            nullable=False,
            server_default="lesson",
        ),
    )

    for spec in SERVICE_TYPES:
        bind.execute(
            sa.text(
                "UPDATE service_types"
                "   SET form_shape = CAST(:form AS service_form),"
                "       updated_at = now()"
                " WHERE code = :code"
            ),
            {"code": spec["code"], "form": spec["form"]},
        )


def downgrade() -> None:
    op.drop_column("service_types", "form_shape")
    sa.Enum(name="service_form").drop(op.get_bind(), checkfirst=True)
