"""Group service types, and add the five that are not about studying

Two things at once, because they cannot be separated. The column alone leaves
every existing row on the `study` default — a catalog whose groups are all
wrong, with nothing erroring — and the new rows alone have nowhere to sit.

The rows are here rather than only in `db/seed.py` for the reason the language
retirement gives: the deploy runs `alembic upgrade head` and never the seed, so
a service type that exists only in the seed reaches every developer's database
and no production one. `tests/test_service_groups.py` fails when the two stop
agreeing.

Revision ID: 146127771c2c
Revises: c3f1a80d47b2
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "146127771c2c"
down_revision: str | Sequence[str] | None = "c3f1a80d47b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


GROUPS = ("study", "entrance", "life")

# Every service type this migration knows about, with the group it belongs to
# and — for the five it creates — the names to create it with. Written out
# rather than imported from `seed.py`: a migration describes the database at
# one moment in time, and one that follows a constant would quietly change
# meaning the next time that constant did.
#
# `names` is absent on the seven that already exist: this migration only moves
# them onto a shelf, it does not rename them.
SERVICE_TYPES: list[dict] = [
    {"code": "tutoring", "group": "study"},
    {"code": "entrance_prep", "group": "entrance"},
    {"code": "language_tutoring", "group": "study"},
    {"code": "exam_live_help", "group": "entrance"},
    {"code": "exam_prep", "group": "study"},
    {"code": "nostrification", "group": "entrance"},
    {"code": "writing", "group": "study"},
    {
        "code": "insurance",
        "group": "life",
        "sort": 8,
        "default_price_unit": "item",
        "names": {
            "ru": ("Страховка", "VZP, PVZP, для визы"),
            "cs": ("Pojištění", "VZP, PVZP, k vízu"),
            "en": ("Insurance", "VZP, PVZP, for the visa"),
            "uk": ("Страхування", "VZP, PVZP, для візи"),
        },
    },
    {
        "code": "bank_letter",
        "group": "life",
        "sort": 9,
        "default_price_unit": "item",
        "names": {
            "ru": ("Справка из банка", "счёт, výpis, для ВНЖ"),
            "cs": ("Potvrzení z banky", "účet, výpis, k pobytu"),
            "en": ("Bank statement", "account, výpis, for the permit"),
            "uk": ("Довідка з банку", "рахунок, výpis, для посвідки"),
        },
    },
    {
        "code": "translation",
        "group": "life",
        "sort": 10,
        "default_price_unit": "item",
        "names": {
            "ru": ("Перевод документов", "с razítkem, судебный"),
            "cs": ("Překlad dokumentů", "s razítkem, soudní"),
            "en": ("Document translation", "stamped, sworn"),
            "uk": ("Переклад документів", "з razítkem, судовий"),
        },
    },
    {
        "code": "residence",
        "group": "life",
        "sort": 11,
        "default_price_unit": "item",
        "names": {
            "ru": ("Виза и ВНЖ", "запись, подача, продление"),
            "cs": ("Vízum a pobyt", "termín, podání, prodloužení"),
            "en": ("Visa and residence", "appointment, filing, renewal"),
            "uk": ("Віза та посвідка", "запис, подання, продовження"),
        },
    },
    {
        "code": "housing",
        "group": "life",
        "sort": 12,
        "default_price_unit": "item",
        "names": {
            "ru": ("Жильё и переезд", "общежитие, договор"),
            "cs": ("Bydlení a stěhování", "kolej, smlouva"),
            "en": ("Housing and moving", "dorm, lease"),
            "uk": ("Житло та переїзд", "гуртожиток, договір"),
        },
    },
]


def upgrade() -> None:
    bind = op.get_bind()

    sa.Enum(*GROUPS, name="service_group").create(bind, checkfirst=True)
    op.add_column(
        "service_types",
        sa.Column(
            "group_code",
            sa.Enum(*GROUPS, name="service_group", create_type=False),
            nullable=False,
            server_default="study",
        ),
    )

    for spec in SERVICE_TYPES:
        if "names" in spec:
            # New. `is_active` and the requires_* flags take the table's own
            # defaults: none of these five needs a subject or an institution,
            # which is the whole point of the group.
            bind.execute(
                sa.text(
                    "INSERT INTO service_types"
                    " (code, group_code, default_price_unit, sort, is_active,"
                    "  created_at, updated_at)"
                    " VALUES (:code, CAST(:group AS service_group), :unit,"
                    "         :sort, true, now(), now())"
                    # Not DO NOTHING: `downgrade` deactivates these five rather
                    # than deleting them, so a database that has been down and
                    # up again already has them — inactive. DO NOTHING would
                    # leave them that way, and the seed that hides the problem
                    # locally does not run on the deployed database.
                    " ON CONFLICT (code) DO UPDATE SET"
                    "   group_code = EXCLUDED.group_code,"
                    "   is_active = true,"
                    "   updated_at = now()"
                ),
                {
                    "code": spec["code"],
                    "group": spec["group"],
                    "unit": spec["default_price_unit"],
                    "sort": spec["sort"],
                },
            )
            for lang, (name, hint) in spec["names"].items():
                bind.execute(
                    sa.text(
                        "INSERT INTO service_type_i18n"
                        " (service_type_id, lang, name, hint)"
                        " SELECT id, CAST(:lang AS ui_lang), :name, :hint"
                        " FROM service_types WHERE code = :code"
                        " ON CONFLICT (service_type_id, lang) DO NOTHING"
                    ),
                    {
                        "code": spec["code"],
                        "lang": lang,
                        "name": name,
                        "hint": hint,
                    },
                )
        else:
            # Existing. Only the shelf moves.
            bind.execute(
                sa.text(
                    "UPDATE service_types SET group_code ="
                    " CAST(:group AS service_group) WHERE code = :code"
                ),
                {"code": spec["code"], "group": spec["group"]},
            )


def downgrade() -> None:
    bind = op.get_bind()

    # Deactivated, not deleted, and only the five this migration created.
    # `offers.service_type_id` is ON DELETE RESTRICT, so a delete would fail
    # the moment anybody had offered one — and taking the row away would strip
    # the offer of its name either way.
    created = [spec["code"] for spec in SERVICE_TYPES if "names" in spec]
    bind.execute(
        sa.text(
            "UPDATE service_types SET is_active = false WHERE code IN :codes"
        ).bindparams(sa.bindparam("codes", value=created, expanding=True))
    )

    op.drop_column("service_types", "group_code")
    sa.Enum(name="service_group").drop(bind, checkfirst=True)
