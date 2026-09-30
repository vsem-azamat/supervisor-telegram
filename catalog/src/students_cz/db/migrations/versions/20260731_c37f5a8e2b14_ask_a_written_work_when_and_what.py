"""Ask a written work when it will be done, and what is taken on

The `work` shape asked for a price and nothing else, so two people who write
theses were one row read twice. Two answers fill it: `offers.turnaround_days`,
and the checklist tables that already exist — the checklist belongs to the
service type rather than to the shape, so written work gets one the same way
the seven errands did.

The rows are spelled out here and not imported from `db/seed.py` for the reason
the previous options migration gives: the deploy runs `alembic upgrade head` and
never the seed, and a migration that follows a constant changes meaning the next
time that constant does. `tests/test_service_groups.py` fails when the two
disagree.

Revision ID: c37f5a8e2b14
Revises: 8c41d2f6b9a7
Create Date: 2026-07-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c37f5a8e2b14"
down_revision: str | Sequence[str] | None = "8c41d2f6b9a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Service type code -> its checklist, each line as (code, ru, cs, en, uk).
SERVICE_OPTIONS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "writing": [
        (
            "semester",
            "Семестровая и реферат",
            "Semestrální práce a referát",
            "Term papers and essays",
            "Семестрова та реферат",
        ),
        (
            "bachelor",
            "Бакалаврская",
            "Bakalářská práce",
            "A bachelor's thesis",
            "Бакалаврська",
        ),
        (
            "master",
            "Дипломная и магистерская",
            "Diplomová práce",
            "A master's thesis",
            "Дипломна та магістерська",
        ),
        (
            "presentation",
            "Презентация к защите",
            "Prezentace k obhajobě",
            "Slides for the defence",
            "Презентація до захисту",
        ),
        (
            "edits",
            "Правки после проверки",
            "Úpravy po připomínkách",
            "Revisions after feedback",
            "Правки після перевірки",
        ),
        (
            "formatting",
            "Оформление по нормам вуза",
            "Formátování dle norem školy",
            "Formatting to the school's rules",
            "Оформлення за нормами вишу",
        ),
    ],
}


def upgrade() -> None:
    op.add_column(
        "offers", sa.Column("turnaround_days", sa.SmallInteger(), nullable=True)
    )
    # NULL already says "we will agree", which is the thing somebody might
    # otherwise reach for a zero to say.
    op.create_check_constraint(
        "turnaround_positive",
        "offers",
        "turnaround_days IS NULL OR turnaround_days > 0",
    )

    bind = op.get_bind()
    for service_code, rows in SERVICE_OPTIONS.items():
        service_id = bind.execute(
            sa.text("SELECT id FROM service_types WHERE code = :code"),
            {"code": service_code},
        ).scalar()
        # Skipped, not asserted, and `writing` is one of the seven that make
        # this necessary: only the five `life` service types are ever created by
        # a migration, so on a migrations-only database (CI, `make db-reset`, a
        # fresh clone) this finds nothing and the seed that runs next creates
        # both the type and its checklist. Asserting aborts the upgrade there.
        if service_id is None:
            continue
        for sort, (option_code, ru, cs, en, uk) in enumerate(rows, start=1):
            option_id = bind.execute(
                sa.text(
                    "INSERT INTO service_options"
                    " (service_type_id, code, sort, is_active, created_at, updated_at)"
                    " VALUES (:service_id, :code, :sort, true, now(), now())"
                    " ON CONFLICT (service_type_id, code) DO UPDATE"
                    "    SET sort = EXCLUDED.sort, is_active = true, updated_at = now()"
                    " RETURNING id"
                ),
                {"service_id": service_id, "code": option_code, "sort": sort},
            ).scalar()
            for lang, label in (("ru", ru), ("cs", cs), ("en", en), ("uk", uk)):
                bind.execute(
                    sa.text(
                        "INSERT INTO service_option_i18n (option_id, lang, label)"
                        " VALUES (:option_id, CAST(:lang AS ui_lang), :label)"
                        " ON CONFLICT (option_id, lang) DO UPDATE"
                        "    SET label = EXCLUDED.label"
                    ),
                    {"option_id": option_id, "lang": lang, "label": label},
                )


def downgrade() -> None:
    op.drop_constraint("turnaround_positive", "offers", type_="check")
    op.drop_column("offers", "turnaround_days")
    # The i18n rows go with them: the foreign key cascades.
    bind = op.get_bind()
    for service_code, rows in SERVICE_OPTIONS.items():
        bind.execute(
            sa.text(
                "DELETE FROM service_options"
                " WHERE code = ANY(:codes)"
                "   AND service_type_id IN"
                "       (SELECT id FROM service_types WHERE code = :service)"
            ),
            {"codes": [row[0] for row in rows], "service": service_code},
        )
