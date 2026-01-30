import logging
from typing import Any, Type

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session, select

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import SessionDep
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    LocationSubType,
    LocationType,
)

router = APIRouter(prefix="/resolve")

logger = logging.getLogger(__name__)


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
) -> ResolvedTypes:
    stmt = select(main_type)

    all_acticity_types = session.exec(stmt).all()

    all_resolved_activities = []
    for _type in all_acticity_types:
        stmt = select(sub_type).where(sub_type.type_id == _type.id)
        all_sub_types = session.exec(stmt).all()
        all_resolved_activities.append(
            ResolvedType(
                id=_type.id,  # type: ignore
                name=_type.name,
                sub_types=[
                    ResolvedSubType(
                        id=st.id,  # type: ignore
                        name=st.name,
                    )
                    for st in all_sub_types
                ],
            )
        )

    return ResolvedTypes(data=all_resolved_activities)


@router.get(
    "/types",
    tags=[Tag.ACTIVITY],
    response_model=ResolvedTypes,
    deprecated=True,
)
@router.get(
    "/activity_types",
    tags=[Tag.ACTIVITY],
    response_model=ResolvedTypes,
)
def get_all_activity_types(session: SessionDep) -> Any:
    return get_resolved_types(session, ActivityType, ActivitySubType)


@router.get(
    "/location_types",
    tags=[Tag.LOCATION],
    response_model=ResolvedTypes,
)
def get_all_location_types(session: SessionDep) -> Any:
    return get_resolved_types(session, LocationType, LocationSubType)
