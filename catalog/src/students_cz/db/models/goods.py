"""Physical things and digital materials.

Deliberately not modelled as offers. A thing has a deposit, a pickup point and
a rental period; a service has an hourly rate and a calendar. Forcing both into
one table would mean half the columns are always null.

The split also matters for money: Telegram requires Stars for digital goods
sold inside a mini app, while physical goods and real-world services are exempt.
Materials therefore carry a Stars price; items never do — they are settled
directly between people and we only publish the contact.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from students_cz.db.base import Base, IdMixin, TimestampMixin
from students_cz.db.models.enums import (
    ContentLang,
    ItemCondition,
    ItemKind,
    ItemStatus,
    MaterialAccess,
    MaterialKind,
    PriceUnit,
    pg_enum,
)


class Item(IdMixin, TimestampMixin, Base):
    """Something physical, offered for rent or for sale."""

    __tablename__ = "items"

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("item_categories.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[ItemKind] = mapped_column(pg_enum(ItemKind, "item_kind"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[ContentLang] = mapped_column(
        pg_enum(ContentLang, "content_lang"),
        nullable=False,
        default=ContentLang.RU,
        server_default="ru",
    )

    # A textbook is about a subject; a laptop is not.
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )

    price_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="CZK"
    )
    price_unit: Mapped[PriceUnit] = mapped_column(
        pg_enum(PriceUnit, "price_unit"),
        nullable=False,
        default=PriceUnit.DAY,
        server_default="day",
    )
    # Held by the owner at handover, never by us. Stated up front because it is
    # usually larger than the rental fee and surprises people otherwise.
    deposit_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))

    condition: Mapped[ItemCondition | None] = mapped_column(
        pg_enum(ItemCondition, "item_condition")
    )
    city: Mapped[str | None] = mapped_column(String(96))
    pickup_note: Mapped[str | None] = mapped_column(String(240))

    # Telegram file_ids rather than our own storage: free CDN, no upload
    # pipeline, and the files are already where the users are.
    photos: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    attrs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    status: Mapped[ItemStatus] = mapped_column(
        pg_enum(ItemStatus, "item_status"),
        nullable=False,
        default=ItemStatus.DRAFT,
        server_default="draft",
    )
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_items_browse", "status", "kind", "category_id"),
        Index("ix_items_city", "city"),
        Index("ix_items_attrs", "attrs", postgresql_using="gin"),
        CheckConstraint(
            "price_amount IS NULL OR price_amount >= 0", name="price_non_negative"
        ),
        CheckConstraint(
            "deposit_amount IS NULL OR deposit_amount >= 0",
            name="deposit_non_negative",
        ),
    )


class Material(IdMixin, TimestampMixin, Base):
    """Something digital: notes, past exams, templates, a course."""

    __tablename__ = "materials"

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), index=True
    )

    kind: Mapped[MaterialKind] = mapped_column(
        pg_enum(MaterialKind, "material_kind"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[ContentLang] = mapped_column(
        pg_enum(ContentLang, "content_lang"),
        nullable=False,
        default=ContentLang.RU,
        server_default="ru",
    )

    # {"file_id": "...", "mime": "application/pdf", "pages": 148} or a list for
    # multi-file bundles.
    files: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    access: Mapped[MaterialAccess] = mapped_column(
        pg_enum(MaterialAccess, "material_access"),
        nullable=False,
        default=MaterialAccess.ON_REQUEST,
        server_default="on_request",
    )
    # Only meaningful once a payment provider is wired up. Kept nullable so the
    # column can sit unused without lying about the current state.
    price_stars: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ItemStatus] = mapped_column(
        pg_enum(ItemStatus, "item_status"),
        nullable=False,
        default=ItemStatus.DRAFT,
        server_default="draft",
    )
    downloads_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (
        Index("ix_materials_browse", "status", "kind", "subject_id"),
        CheckConstraint("price_stars IS NULL OR price_stars > 0", name="stars_positive"),
        CheckConstraint(
            "access <> 'paid' OR price_stars IS NOT NULL",
            name="paid_needs_price",
        ),
    )


__all__ = ["Item", "Material"]
