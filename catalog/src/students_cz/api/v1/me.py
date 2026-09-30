"""The account behind the init data: who you are, and what you chose."""

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from students_cz.api.deps import (
    LangDep,
    SessionDep,
    SettingsDep,
    UserDep,
    is_operator,
)
from students_cz.api.v1.taxonomy import institution_out
from students_cz.db.models import (
    HelperProfile,
    Institution,
)
from students_cz.schemas import (
    MeOut,
    MeUpdate,
)
from students_cz.services.catalog import avatar_for
from students_cz.services.people import full_name, update_profile

router = APIRouter()


@router.get("/me", response_model=MeOut, tags=["me"])
async def read_me(
    user: UserDep, session: SessionDep, lang: LangDep, settings: SettingsDep
) -> MeOut:
    helper = await session.get(HelperProfile, user.id)
    institution = None
    if user.institution_id:
        row = await session.scalar(
            select(Institution)
            .where(Institution.id == user.institution_id)
            .options(selectinload(Institution.names))
        )
        if row:
            institution = institution_out(row, lang)

    return MeOut(
        id=user.id,
        tg_id=user.tg_id,
        name=full_name(user),
        username=user.tg_username,
        avatar=avatar_for(user),
        ui_lang=user.ui_lang,
        spoken_langs=list(user.spoken_langs),
        city=user.city,
        institution=institution,
        is_helper=helper is not None,
        helper_status=helper.status.value if helper else None,
        is_admin=is_operator(user, settings),
    )


@router.patch("/me", response_model=MeOut, tags=["me"])
async def update_me(
    payload: MeUpdate,
    user: UserDep,
    session: SessionDep,
    lang: LangDep,
    settings: SettingsDep,
) -> MeOut:
    await update_profile(session, user, payload)
    # The language the payload just set, not the one the request arrived with:
    # `LangDep` was resolved before the change, so reading it back through the
    # old one would answer the screen in the language it just left.
    return await read_me(user, session, payload.ui_lang or lang, settings)
