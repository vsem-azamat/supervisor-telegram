"""Turning a reference row into the name a person reads.

Every reference table — service types, subjects, institutions, languages, item
categories — keeps its names in a side table with one row per language. Two
questions come up on nearly every screen: what does this row read as, and what
do these twenty ids read as. Both live here, with one asymmetry worth knowing
before reaching for the second: `translated` and `short_form` work on any of
them, because all they read is `names`, while `rows_by_id` and `names_by_id`
ask for an `id` and so cannot serve `Language`, which is keyed by its code.

They live here because the alternative was `catalog._localised`, a private
symbol imported by name across the package boundary at sixteen call sites,
with three more hand-rolled "fetch the names for these ids" helpers alongside
it. Five modules read names off the taxonomy now, and a rule five modules need
is a rule, not a private helper of whichever module happened to write it first.

Nothing here takes a `UiLang` on faith: a row with no translation in the asked
language falls back to any translation it has, because a missing Ukrainian name
should show the Czech one rather than an empty row.
"""

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from students_cz.db.models.enums import UiLang


class Named(Protocol):
    """A reference row with a `names` collection loaded.

    Structural rather than a base class: the reference tables share the shape
    but not an ancestor, and this module only ever reads. `names` is the whole
    requirement — `Language` is keyed by its code and has no `id` at all, so
    asking for one here would exclude a table that translates exactly like the
    others.
    """

    names: Any


def translated(row: Named, lang: UiLang, attr: str = "name") -> str | None:
    """Pick a translation of one attribute, falling back to any that exists.

    `attr` because the i18n row carries more than the name — a hint under a
    service type, an institution's short form — and each of them wants the same
    fallback.
    """
    for candidate in row.names:
        if candidate.lang == lang:
            value = getattr(candidate, attr, None)
            if value:
                return value
    for candidate in row.names:
        value = getattr(candidate, attr, None)
        if value:
            return value
    return None


def short_form(row: Named, lang: UiLang) -> str | None:
    """What an institution is called where there is no room for its full name.

    "ČVUT" fits in a chip and on a card; "České vysoké učení technické v Praze"
    does not, and truncating it loses the only part anybody recognises. Falls
    back to the full name for the institutions that have no short one.
    """
    return translated(row, lang, "short_name") or translated(row, lang)


async def rows_by_id(session: AsyncSession, model: Any, ids: Any) -> dict[int, Any]:
    """The rows for a set of ids, names loaded, keyed by id.

    One query for a whole page rather than one per row. `None` is a legal id
    here — an offer without a subject, a request without an institution — and
    is dropped rather than asked about.

    The id-keyed tables only — this asks for `model.id`, and `Language` is
    keyed by its code. `translated` and `short_form` above serve every
    reference table, because they only read `names`, so the split is real and
    this is the half of the module that does not cover all of them. `model` is
    untyped because a declarative class is not a `type[Named]` to a checker;
    the cost is that handing this the wrong table fails at runtime rather than
    at the call site.
    """
    wanted = {value for value in ids if value is not None}
    if not wanted:
        return {}
    rows = await session.scalars(
        select(model).where(model.id.in_(wanted)).options(selectinload(model.names))
    )
    return {row.id: row for row in rows}


async def names_by_id(
    session: AsyncSession, model: Any, ids: Any, lang: UiLang
) -> dict[int, str]:
    """The same, already rendered to names — and the same tables.

    Empty string rather than `None` for a row with no translation at all, so a
    caller filling a field that must be a string does not have to say so again.
    """
    rows = await rows_by_id(session, model, ids)
    return {row_id: translated(row, lang) or "" for row_id, row in rows.items()}
