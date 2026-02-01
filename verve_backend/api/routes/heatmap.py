import importlib.resources
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import col, func, select, text, tuple_
from starlette.status import (
    HTTP_400_BAD_REQUEST,
)

from verve_backend.api.common.utils import check_and_raise_primary_key
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import Activity, ActivitySubType, ActivityType, UserSettings


class HeatMapResponse(BaseModel):
    points: list[tuple[float, float, float]]
    center: tuple[float, float] | None


router = APIRouter(
    prefix="/heatmap",
    tags=[Tag.TRACK, Tag.ACTIVITY, Tag.HEATMAP],
)


@router.get("/activities", response_model=HeatMapResponse)
def get_heatmap(
    user_session: UserSession,
    year: Annotated[int | None, Query(ge=2000)] = None,
    month: Annotated[int | None, Query(ge=1, lt=13)] = None,
    activity_type_id: int | None = None,
    activity_sub_type_id: int | None = None,
    limit: int | None = None,
) -> Any:
    _user_id, session = user_session
    user_id = UUID(_user_id)

    check_and_raise_primary_key(session, ActivityType, activity_type_id)
    if activity_type_id is None and activity_sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    check_and_raise_primary_key(session, ActivitySubType, activity_sub_type_id)
    if year is None and month is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Year must be set when month is set",
        )

    settings = session.get(UserSettings, user_id)
    assert settings
    exclude_types = settings.heatmap_settings.excluded_activity_types

    sel_ids = None
    if activity_type_id or limit or year or month:
        query = select(Activity.id)
        if activity_type_id:
            query = query.where(Activity.type_id == activity_type_id)
        if activity_sub_type_id:
            query = query.where(Activity.sub_type_id == activity_sub_type_id)
        if year is not None:
            query = query.where(func.extract("year", Activity.start) == year)  # type: ignore
            if month is not None:
                query = query.where(func.extract("month", Activity.start) == month)  # type: ignore

        if exclude_types:
            query = query.where(
                tuple_(Activity.type_id, Activity.sub_type_id).notin_(exclude_types)  # type: ignore
            )

        query = query.order_by(col(Activity.start).desc())

        if limit:
            query = query.limit(limit)
        sel_ids = session.exec(query).all()
        if not sel_ids:
            return HeatMapResponse(points=[], center=None)
    else:
        if exclude_types:
            query = select(Activity.id).where(
                tuple_(Activity.type_id, Activity.sub_type_id).notin_(exclude_types)  # type: ignore
            )
            _sel_ids = session.exec(query).all()
            if _sel_ids:
                sel_ids = _sel_ids

    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("aggregate_activity_heatmap.sql")
        .read_text()
    )

    data = session.exec(
        text(stmt),  # type: ignore
        params={"activity_ids": sel_ids},
    ).all()

    return HeatMapResponse(
        points=data,
        # NOTE: Use the max point as center
        center=(data[0][0], data[0][1]) if data else None,
    )
