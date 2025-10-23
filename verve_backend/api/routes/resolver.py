import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import SessionDep
from verve_backend.models import ActivitySubType, ActivityType

router = APIRouter(prefix="/resolve")

logger = logging.getLogger("uvicorn.error")


class ResolvedSubType(BaseModel):
    id: int
    name: str


class ResolvedActivity(BaseModel):
    id: int
    name: str
    sub_types: list[ResolvedSubType]


class ResolvedActivities(BaseModel):
    data: list[ResolvedActivity]


@router.get(
    "/types",
    tags=[Tag.ACTIVITY],
    response_model=ResolvedActivities,
)
def get_all_types(session: SessionDep) -> Any:
    stmt = select(ActivityType)

    all_acticity_types = session.exec(stmt).all()

    all_resolved_activities = []
    for _type in all_acticity_types:
        stmt = select(ActivitySubType).where(ActivitySubType.type_id == _type.id)
        all_sub_types = session.exec(stmt).all()
        all_resolved_activities.append(
            ResolvedActivity(
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

    return ResolvedActivities(data=all_resolved_activities)
