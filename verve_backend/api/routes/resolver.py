from typing import Any, Type, cast

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session, select

from verve_backend.api.common.locale import CatalogLocale, load_translations
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import OptionalCurrentUser, SessionDep
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    LocationSubType,
    LocationType,
    SupportedLocale,
    User,
    UserSettings,
)

router = APIRouter(prefix="/resolve")


class ResolvedSubType(BaseModel):
    id: int
    name: str


class ResolvedType(BaseModel):
    id: int
    name: str
    sub_types: list[ResolvedSubType]


class ResolvedTypes(BaseModel):
    data: list[ResolvedType]


def get_resolved_types(
    session: Session,
    main_type: Type[ActivityType] | Type[LocationType],
    sub_type: Type[ActivitySubType] | Type[LocationSubType],
    locale: SupportedLocale,
    domain: str,
) -> ResolvedTypes:
    localized = load_translations(locale).get(domain, {})
    english = load_translations(SupportedLocale.EN).get(domain, {})

    def label(parent: str, child: str | None = None) -> str:
        def lookup(catalog: dict) -> str | None:
            entry = catalog.get(parent, {})
            return (
                entry.get("name")
                if child is None
                else entry.get("sub_types", {}).get(child)
            )

        return (
            lookup(localized)
            or lookup(english)
            or (child if child is not None else parent)
        )

    stmt = select(main_type)

    all_acticity_types = session.exec(stmt).all()

    # Queried rows have populated primary keys, unlike unsaved activity models.
    all_resolved_activities = []
    for _type in all_acticity_types:
        stmt = select(sub_type).where(sub_type.type_id == _type.id)
        all_sub_types = session.exec(stmt).all()
        all_resolved_activities.append(
            ResolvedType(
                id=cast(int, _type.id),
                name=label(_type.name),
                sub_types=[
                    ResolvedSubType(
                        id=cast(int, st.id),
                        name=label(_type.name, st.name),
                    )
                    for st in all_sub_types
                ],
            )
        )

    return ResolvedTypes(data=all_resolved_activities)


def resolve_locale(
    session: Session, user: User | None, locale: SupportedLocale | None
) -> SupportedLocale:
    if locale is not None:
        return locale
    settings = session.get(UserSettings, user.id) if user is not None else None
    return settings.locale if settings is not None else SupportedLocale.EN


@router.get(
    "/types",
    tags=[Tag.ACTIVITY],
    response_model=ResolvedTypes,
    deprecated=True,
    operation_id="get_all_activity_types_deprecated",
    openapi_extra={"security": [{}]},
)
@router.get(
    "/activity_types",
    tags=[Tag.ACTIVITY],
    response_model=ResolvedTypes,
    openapi_extra={"security": [{}]},
)
def get_all_activity_types(
    session: SessionDep, user: OptionalCurrentUser, locale: CatalogLocale = None
) -> Any:
    return get_resolved_types(
        session,
        ActivityType,
        ActivitySubType,
        resolve_locale(session, user, locale),
        "activity_types",
    )


@router.get(
    "/location_types",
    tags=[Tag.LOCATION],
    response_model=ResolvedTypes,
    openapi_extra={"security": [{}]},
)
def get_all_location_types(
    session: SessionDep, user: OptionalCurrentUser, locale: CatalogLocale = None
) -> Any:
    return get_resolved_types(
        session,
        LocationType,
        LocationSubType,
        resolve_locale(session, user, locale),
        "location_types",
    )
