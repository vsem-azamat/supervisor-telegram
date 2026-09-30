"""Say what an errand covers, and let a person add their own words

An errand has no axes — the tile is the whole query — so somebody offering
insurance could say nothing beyond the word "insurance". Two things fix that: a
checklist per service type, translated like every other name we author, and a
free-text note on the offer for what the checklist could not say.

The rows are here and not only in `db/seed.py` for the reason the grouping
migration gives: the deploy runs `alembic upgrade head` and never the seed, so a
checklist that exists only in the seed is one every developer sees and no student
does. `tests/test_service_groups.py` fails when the two disagree.

Revision ID: 8c41d2f6b9a7
Revises: 5b2a9c41e7d3
Create Date: 2026-07-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c41d2f6b9a7"
down_revision: str | Sequence[str] | None = "5b2a9c41e7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Service type code -> its checklist, each line as
# (code, ru, cs, en, uk). A constant of its own rather than a reference to the
# seed: a migration describes the database at one moment, and one that follows a
# constant changes meaning the next time that constant does.
SERVICE_OPTIONS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "insurance": [
        ("vzp_pvzp", "Оформлю VZP или PVZP", "Vyřídím VZP nebo PVZP", "I arrange VZP or PVZP", "Оформлю VZP або PVZP"),
        ("for_visa", "Для визы и продления", "K vízu a k prodloužení", "For the visa and its renewal", "Для візи та продовження"),
        ("choose_plan", "Помогу выбрать тариф", "Poradím s tarifem", "I help you pick a plan", "Допоможу обрати тариф"),
        ("go_with", "Схожу вместе в офис", "Půjdu s tebou na pobočku", "I come to the office with you", "Схожу разом до офісу"),
    ],
    "bank_letter": [
        ("open_account", "Открою счёт вместе с тобой", "Otevřu s tebou účet", "I open the account with you", "Відкрию рахунок разом з тобою"),
        ("statement", "Возьму выписку для ВНЖ", "Zařídím výpis k pobytu", "I get the statement for your permit", "Візьму виписку для посвідки"),
        ("go_with", "Схожу вместе в банк", "Půjdu s tebou do banky", "I come to the bank with you", "Схожу разом до банку"),
    ],
    "translation": [
        ("sworn", "Судебный перевод с печатью", "Soudní překlad s razítkem", "Sworn translation with a stamp", "Судовий переклад з печаткою"),
        ("diploma", "Диплом и аттестат", "Diplom a vysvědčení", "Diplomas and school certificates", "Диплом і атестат"),
        ("notary", "Нотариальное заверение", "Notářské ověření", "Notarised certification", "Нотаріальне засвідчення"),
    ],
    "residence": [
        ("appointment", "Запишу на подачу", "Objednám tě k podání", "I book your appointment", "Запишу на подання"),
        ("documents", "Соберу пакет документов", "Připravím složku dokumentů", "I put the paperwork together", "Зберу пакет документів"),
        ("interpreter", "Схожу вместе как переводчик", "Půjdu s tebou jako tlumočník", "I come along as your interpreter", "Схожу разом як перекладач"),
        ("renewal", "Продление визы и ВНЖ", "Prodloužení víza a pobytu", "Renewing a visa or a permit", "Продовження візи та посвідки"),
    ],
    "housing": [
        ("dormitory", "Общежитие", "Kolej", "A dormitory place", "Гуртожиток"),
        ("flat", "Поиск квартиры", "Hledání bytu", "Finding a flat", "Пошук квартири"),
        ("contract", "Проверю договор", "Zkontroluju smlouvu", "I check the contract", "Перевірю договір"),
        ("moving", "Помогу с переездом", "Pomůžu se stěhováním", "I help with the move", "Допоможу з переїздом"),
    ],
    "nostrification": [
        ("papers", "Подам документы", "Podám dokumenty", "I file the documents", "Подам документи"),
        ("exams", "Подготовлю к досдаче предметов", "Připravím na dozkoušení předmětů", "I prepare you for the make-up exams", "Підготую до складання предметів"),
        ("school", "Аттестат", "Vysvědčení ze střední", "A school certificate", "Атестат"),
        ("university", "Диплом", "Vysokoškolský diplom", "A university diploma", "Диплом"),
    ],
    "exam_live_help": [
        ("on_call", "На связи весь экзамен", "Na příjmu po celou zkoušku", "On call for the whole exam", "На зв'язку весь іспит"),
        ("prep", "Разберу задание заранее", "Projdu zadání předem", "I go through the paper beforehand", "Розберу завдання заздалегідь"),
        ("night", "Ночью и в выходные", "V noci i o víkendu", "Nights and weekends", "Вночі та у вихідні"),
    ],
}


def upgrade() -> None:
    op.create_table(
        "service_options",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "service_type_id",
            sa.BigInteger(),
            sa.ForeignKey("service_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("service_type_id", "code", name="uq_service_options_code"),
    )
    op.create_table(
        "service_option_i18n",
        sa.Column(
            "option_id",
            sa.BigInteger(),
            sa.ForeignKey("service_options.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "lang",
            # The type already exists; naming its members again would try to
            # create it a second time.
            postgresql.ENUM("ru", "cs", "en", "uk", name="ui_lang", create_type=False),
            primary_key=True,
        ),
        sa.Column("label", sa.String(160), nullable=False),
    )

    op.add_column(
        "offers",
        sa.Column(
            "option_ids",
            postgresql.ARRAY(sa.BigInteger()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("offers", sa.Column("note", sa.Text(), nullable=True))
    # The question worth asking of this column is "who does X", which an
    # overlap test answers and a sequential scan does not.
    op.create_index(
        "ix_offers_options", "offers", ["option_ids"], postgresql_using="gin"
    )

    bind = op.get_bind()
    for service_code, rows in SERVICE_OPTIONS.items():
        service_id = bind.execute(
            sa.text("SELECT id FROM service_types WHERE code = :code"),
            {"code": service_code},
        ).scalar()
        # Skipped, not asserted. Only five of the twelve service types are ever
        # created by a migration — the five `life` ones — and the other seven
        # exist in `db/seed.py` alone. That gap is documented in
        # docs/data-model.md: they reached production because somebody ran the
        # seed against it by hand, so this loop finds them there, while on a
        # migrations-only database (CI, `make db-reset`, a fresh clone) it does
        # not, and the seed that runs next creates both the type and its
        # checklist. Asserting here aborts `alembic upgrade head` on every one
        # of those.
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
    op.drop_index("ix_offers_options", table_name="offers")
    op.drop_column("offers", "note")
    op.drop_column("offers", "option_ids")
    op.drop_table("service_option_i18n")
    op.drop_table("service_options")
