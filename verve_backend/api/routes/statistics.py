import importlib.resources
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any, Generic, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import func, select, text
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_501_NOT_IMPLEMENTED,
)

from verve_backend.api.common.db_utils import check_and_raise_primary_key
from verve_backend.api.deps import UserSession
from verve_backend.core.date_utils import get_week_date_range
from verve_backend.models import Activity, ActivityType, UserSettings

T = TypeVar("T")


# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/statistics", tags=["statistics"])


class StatsParam(BaseModel):
    top_n: int
    year: int = Field(default=datetime.now().year)
    activity_type_id: int | None = None
    activity_sub_type_id: int | None = None


class MetricSummary(BaseModel, Generic[T]):
    total: T
    per_type: dict[int, T]
    per_sub_type: dict[int, dict[int | None, T]]


class YearStatsResponse(BaseModel):
    distance: MetricSummary[float]
    duration: MetricSummary[int]
    count: MetricSummary[int]


class WeekStatsResponse(BaseModel):
    distance: dict[datetime, float | None]
    elevation_gain: dict[datetime, float | None]
    duration: dict[datetime, int | None]


@router.get("/weekly")
def get_weekly_stats(
    user_session: UserSession,
    params: StatsParam = Depends(),
) -> Any:
    _, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get("/year", response_model=YearStatsResponse)
def get_year_stats(
    user_session: UserSession,
    year: Annotated[int | None, Query(ge=2000)] = None,
) -> Any:
    _, session = user_session

    stmt = select(  # type: ignore
        Activity.type_id,
        Activity.sub_type_id,
        func.count().label("count"),
        func.sum(Activity.distance).label("total_distance"),
        func.sum(Activity.duration).label("total_duration"),
    ).group_by(Activity.type_id, Activity.sub_type_id)
    if year is not None:
        stmt = stmt.where(func.extract("year", Activity.start) == year)  # type: ignore
    data = session.exec(stmt).all()

    per_type_distance = cast(
        dict[int, dict[int | None, float]], defaultdict(lambda: defaultdict(dict))
    )
    per_type_duration = cast(
        dict[int, dict[int | None, int]], defaultdict(lambda: defaultdict(dict))
    )
    per_type_count = cast(
        dict[int, dict[int | None, int]], defaultdict(lambda: defaultdict(dict))
    )

    total_type_distance = defaultdict(float)
    total_type_duration = defaultdict(int)
    total_type_count = defaultdict(int)
    for row in data:
        _type_id, _sub_type_id, _count, _distance, _duration = cast(
            tuple[int, int | None, int, float, timedelta], row
        )
        per_type_distance[_type_id][_sub_type_id] = _distance
        per_type_duration[_type_id][_sub_type_id] = round(_duration.total_seconds())
        per_type_count[_type_id][_sub_type_id] = _count

        total_type_distance[_type_id] += _distance
        total_type_duration[_type_id] += round(_duration.total_seconds())
        total_type_count[_type_id] += _count

    resp = YearStatsResponse(
        distance=MetricSummary(
            total=sum(total_type_distance.values()),
            per_type=total_type_distance,
            per_sub_type=per_type_distance,
        ),
        duration=MetricSummary(
            total=sum(total_type_duration.values()),
            per_type=total_type_duration,
            per_sub_type=per_type_duration,
        ),
        count=MetricSummary(
            total=sum(total_type_count.values()),
            per_type=total_type_count,
            per_sub_type=per_type_count,
        ),
    )

    return resp


@router.get("/week", response_model=WeekStatsResponse)
def get_week_stats(
    user_session: UserSession,
    year: Annotated[int | None, Query(ge=2000)] = None,
    week: Annotated[int | None, Query(ge=1, le=53)] = None,
    activity_type_id: int | None = None,
) -> Any:
    user_id, session = user_session

    settings = session.get(UserSettings, user_id)
    assert settings

    _activity_type_id = (
        settings.default_type_id if activity_type_id is None else activity_type_id
    )
    check_and_raise_primary_key(session, ActivityType, _activity_type_id)

    if year is None and week is None:
        iso_cal = datetime.now().isocalendar()
        week = iso_cal.week
        year = iso_cal.year
        logger.debug("Current week/year used: %d/%d", week, year)

    if year is None or week is None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Both year and week must be set.",
        )

    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("select_weekly_activity_data.sql")
        .read_text()
    )

    data = session.exec(
        text(stmt),  # type: ignore
        params={
            "week": week,
            "year": year,
            "activity_type_id": _activity_type_id,
        },
    ).all()

    week_start, _ = get_week_date_range(year, week)
    _response = {
        key: {week_start + timedelta(days=i): None for i in range(7)}
        for key in ["distance", "elevation_gain", "duration"]
    }
    for date, _dist, _ele, _ts in data:
        _response["distance"][date] = _dist
        _response["elevation_gain"][date] = _ele
        _response["duration"][date] = _ts.total_seconds()

    return WeekStatsResponse.model_validate(_response)
