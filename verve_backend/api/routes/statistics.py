import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any, Generic, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import func, select
from starlette.status import (
    HTTP_501_NOT_IMPLEMENTED,
)

from verve_backend.api.deps import UserSession
from verve_backend.models import Activity

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
