"""Offers — where the three axes of the catalog intersect.

Every search the product performs is an intersection of *subject*, *institution
context* and *kind of help*: "calculus × ČVUT FEL × live exam help". The legacy
schema modelled this as two parallel branches (``LessonsUniversity`` and
``LessonsLanguage``) with a join table each, so adding a third kind of help
meant adding another pair of tables. Here a new kind of help is one row in
``service_types``.
"""

from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from students_cz.db.base import Base, IdMixin, TimestampMixin
from students_cz.db.models.enums import PriceUnit, WorkFormat, pg_enum

if TYPE_CHECKING:
    from students_cz.db.models.people import HelperProfile


class Offer(IdMixin, TimestampMixin, Base):
    __tablename__ = "offers"

    helper_id: Mapped[int] = mapped_column(
        ForeignKey("helper_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False
    )
    # Both nullable on purpose: "write my thesis" needs no subject, and a tutor
    # may teach calculus without tying it to one school. The service type's
    # requires_* flags decide what the form demands.
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT")
    )
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT")
    )

    price_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="CZK"
    )
    price_unit: Mapped[PriceUnit] = mapped_column(
        pg_enum(PriceUnit, "price_unit"),
        nullable=False,
        default=PriceUnit.HOUR,
        server_default="hour",
    )

    # Languages this particular offer is delivered in. Usually equals the
    # helper's spoken languages, but not always — someone may tutor maths in
    # Russian while teaching Czech only in Czech.
    langs: Mapped[list[str]] = mapped_column(
        ARRAY(String(8)), nullable=False, server_default="{}"
    )
    work_format: Mapped[WorkFormat] = mapped_column(
        pg_enum(WorkFormat, "work_format"),
        nullable=False,
        default=WorkFormat.BOTH,
        server_default="both",
    )

    # Per-service-type extras that do not deserve columns: exam board, page
    # count, whether a trial lesson is free.
    attrs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Which lines of the service type's checklist this offer covers. Ids rather
    # than a join table, the same shape as `langs` above and indexed the same
    # way: the question worth asking of them is "who does X", which an overlap
    # test answers. A retired option is deactivated rather than deleted, so this
    # array never points at a label that is gone.
    option_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default="{}"
    )
    # What the checklist could not say, in the person's own words. Read, not
    # matched — the checklist is the part search can use.
    note: Mapped[str | None] = mapped_column(Text)

    # How long the work takes. Only a written work asks — a lesson happens when
    # the two of them agree and an errand takes as long as the office queue.
    # NULL is an answer and not a gap: it says the two of them will agree.
    #
    # A column rather than a key in `attrs` above, which names exactly this as
    # its example, because `attrs` is exposed by no schema and the question
    # worth asking here is a range: who can do it inside a week. Unindexed until
    # something asks it — see docs/data-model.md.
    turnaround_days: Mapped[int | None] = mapped_column(SmallInteger)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    helper: Mapped["HelperProfile"] = relationship(back_populates="offers")

    __table_args__ = (
        # NULLS NOT DISTINCT (Postgres 15+) is what makes this work: without it
        # a helper could add "calculus, no institution" twice, because two NULLs
        # would count as different values.
        UniqueConstraint(
            "helper_id",
            "service_type_id",
            "subject_id",
            "institution_id",
            name="uq_offers_axes",
            postgresql_nulls_not_distinct=True,
        ),
        # The catalog's main access path: everyone offering X, cheapest first.
        Index(
            "ix_offers_lookup",
            "service_type_id",
            "subject_id",
            "institution_id",
            "is_active",
        ),
        Index("ix_offers_helper", "helper_id"),
        # "Who goes with you to the bank" is an overlap test, which is what a
        # GIN index answers and a sequential scan does not.
        Index("ix_offers_options", "option_ids", postgresql_using="gin"),
        # The commonest query of all is "everyone who teaches X", with no kind
        # of help named. ix_offers_lookup leads with service_type_id and so
        # cannot serve it.
        Index("ix_offers_subject", "subject_id", "is_active"),
        Index("ix_offers_langs", "langs", postgresql_using="gin"),
        Index("ix_offers_attrs", "attrs", postgresql_using="gin"),
        Index("ix_offers_price", "price_currency", "price_amount"),
        CheckConstraint(
            "price_amount IS NULL OR price_amount >= 0", name="price_non_negative"
        ),
        # Zero days and minus three days are not answers, and NULL already says
        # the thing somebody might reach for zero to say.
        CheckConstraint(
            "turnaround_days IS NULL OR turnaround_days > 0",
            name="turnaround_positive",
        ),
    )
