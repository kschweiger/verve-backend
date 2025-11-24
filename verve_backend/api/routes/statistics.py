import importlib.resources
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
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
from verve_backend.core.date_utils import get_month_grid, get_week_date_range
from verve_backend.models import Activity, ActivityType, UserSettings
from verve_backend.transformations import CalendarWeek, build_calendar_response

T = TypeVar("T", int, float)


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


class WeekMetric(BaseModel, Generic[T]):
    per_day: dict[date, T | None]
    pie_data: dict[int | None, float]
    total: T


class WeekStatsResponse(BaseModel):
    distance: WeekMetric[float]
    elevation_gain: WeekMetric[float]
    duration: WeekMetric[int]


class CalendarResponse(BaseModel):
    """Calendar data organized by weeks."""

    year: int
    month: int
    weeks: Annotated[list[CalendarWeek], Field(min_length=4, max_length=6)]


def process_metric_data(
    per_day: dict[date, T | None],
    pie_data: dict[int | None, float],
) -> WeekMetric[T]:
    """Convert pie data to percentages and calculate totals for a single metric."""
    # Calculate total from per_day data
    total = sum(v for v in per_day.values() if v is not None)

    # Convert to percentages
    pie_percentages = {}
    if total > 0:
        for sub_type_id, value in pie_data.items():
            pie_percentages[sub_type_id] = (value / total) * 100
    else:
        pie_percentages = dict(pie_data)

    return WeekMetric(
        per_day=per_day,
        pie_data=pie_percentages,
        total=total,
    )


@router.get("/weekly")
def get_weekly_stats(
    user_session: UserSession,
    params: StatsParam = Depends(),
) -> Any:
    _, session = user_session  # noqa: RUF059
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

    distance_per_day: dict[date, float | None] = {
        week_start + timedelta(days=i): None for i in range(7)
    }
    elevation_gain_per_day: dict[date, float | None] = {
        week_start + timedelta(days=i): None for i in range(7)
    }
    duration_per_day: dict[date, int | None] = {
        week_start + timedelta(days=i): None for i in range(7)
    }

    distance_pie: dict[int | None, float] = defaultdict(float)
    elevation_gain_pie: dict[int | None, float] = defaultdict(float)
    duration_pie: dict[int | None, float] = defaultdict(float)

    for _date, _sub_type_id, _dist, _ele, _ts in data:
        distance_per_day[_date] = _dist
        elevation_gain_per_day[_date] = _ele
        duration_per_day[_date] = round(_ts.total_seconds())

        distance_pie[_sub_type_id] += _dist
        elevation_gain_pie[_sub_type_id] += _ele
        duration_pie[_sub_type_id] += _ts.total_seconds()

    return WeekStatsResponse(
        distance=process_metric_data(distance_per_day, distance_pie),
        elevation_gain=process_metric_data(elevation_gain_per_day, elevation_gain_pie),
        duration=process_metric_data(duration_per_day, duration_pie),
    )


@router.get("/calender", response_model=CalendarResponse)
def get_calendar(
    user_session: UserSession,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    year: Annotated[int | None, Query(ge=2000)] = None,
) -> Any:
    _, session = user_session

    today = datetime.now()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    month_date_grid = get_month_grid(year, month)

    first_date = month_date_grid[0][0]
    last_date = month_date_grid[-1][-1]

    stmt = (
        select(Activity)
        .where(Activity.start >= first_date)
        .where(Activity.start <= last_date)
    )
    activities = session.exec(stmt).all()
    weeks = build_calendar_response(activities, month_date_grid, month)

    return CalendarResponse(year=year, month=month, weeks=weeks)
