import importlib.resources
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Generic, Self, TypeVar, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session, func, select, text
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_501_NOT_IMPLEMENTED,
)

from verve_backend.api.common.utils import check_and_raise_primary_key
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.core.date_utils import (
    get_month_grid,
    get_week_date_range,
    iso_week_date_weeks_ago_berlin,
)
from verve_backend.models import Activity, ActivityType, UserSettings
from verve_backend.transformations import CalendarWeek, build_calendar_response

T = TypeVar("T", int, float)


logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/statistics", tags=[Tag.STATISTICS])


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


def valid_month(value: int | None) -> int | None:
    if value is None:
        return value
    if value >= 1 and value <= 12:
        return value

    raise ValueError("Month must be between 1 and 12")


class GridDay(BaseModel):
    """Aggregated activity values for one calendar day."""

    date: date
    activity_count: int
    duration_seconds: int


class GridWeek(BaseModel):
    """One Monday-starting calendar week in the activity grid.

    Contract:
    - days always has exactly seven entries, ordered Monday through Sunday.
    - A GridDay entry represents a past or current date.
    - null is only used for future dates in the trailing/current week.
    - Past dates without activity are GridDay entries with zero values.
    """

    start_date: date = Field(description="Monday date for this week.")
    month: Annotated[int | None, valid_month] = Field(
        description=(
            "Month number to label this week when this week's Monday starts the first "
            "displayed week for that month, or null when no label should be shown."
        )
    )
    days: list[GridDay | None] = Field(
        min_length=7,
        max_length=7,
        description=(
            "Seven entries ordered Monday through Sunday. Null is only allowed for "
            "future dates, normally at the end of the current week."
        ),
    )

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        first_day = self.days[0]
        if first_day is None:
            raise ValueError("First day of the week cannot be None")
        if self.month and first_day.date.month != self.month:
            raise ValueError("First day of the week must match the month label")
        if self.start_date != first_day.date:
            raise ValueError("Start date must match the date of the first day")
        return self


class GridMax(BaseModel):
    activity_count: int
    duration_seconds: int


class GridTotals(BaseModel):
    activity_count: int
    duration_seconds: int
    active_days: int


class GridSummary(BaseModel):
    last_active_day: date | None
    week_activity_streak: int = Field(ge=0)
    activities_this_month: int = Field(ge=0)


class ActivityGridResponse(BaseModel):
    weeks: list[GridWeek] = Field(min_length=1)
    scale_max: GridMax
    totals: GridTotals
    summary: GridSummary

    @field_validator("weeks", mode="after")
    @classmethod
    def validate_weeks(cls, weeks: list[GridWeek]) -> list[GridWeek]:
        last_week = weeks[-1]

        seen_none = False
        for day in last_week.days:
            if day is None:
                seen_none = True
            elif seen_none:
                raise ValueError("None is only allowed as trailing values in last week")

        for week in weeks[0:-1]:
            if any(d is None for d in week.days):
                raise ValueError("None is only allowed in last week")

        return weeks


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
            tuple[int, int | None, int, float | None, timedelta], row
        )
        if _distance is not None:
            per_type_distance[_type_id][_sub_type_id] = _distance
        per_type_duration[_type_id][_sub_type_id] = round(_duration.total_seconds())
        per_type_count[_type_id][_sub_type_id] = _count

        if _distance is not None:
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
        if _dist is not None:
            distance_per_day[_date] = _dist
        if _ele is not None:
            elevation_gain_per_day[_date] = _ele
        duration_per_day[_date] = round(_ts.total_seconds())

        if _dist is not None:
            distance_pie[_sub_type_id] += _dist
        if _ele is not None:
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


def _find_grid_start_end(
    weeks: int,
) -> tuple[date, date]:
    """Calculate the start and end date for the activity grid based on the number of
    weeks."""
    start_date = iso_week_date_weeks_ago_berlin(weeks_back=weeks)
    today = datetime.now().date()
    end_date = datetime.fromisocalendar(
        year=today.year, week=today.isocalendar().week, day=7
    ).date()

    return start_date, end_date


def _run_query(session: Session, file_name: str, params: dict) -> tuple:
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath(file_name)
        .read_text()
    )

    _data = session.exec(
        text(stmt),  # type: ignore
        params=params,
    ).first()

    return _data


@router.get("/activity-grid", response_model=ActivityGridResponse)
def get_activity_grid(
    user_session: UserSession,
    weeks: int = 52,
) -> Any:
    _user_id, session = user_session
    start_date, end_date = _find_grid_start_end(weeks)
    today = datetime.now().date()
    stmt = (
        select(
            func.date(Activity.start).label("date"),
            func.count().label("activity_count"),
            func.sum(Activity.duration).label("total_duration"),
        )
        .where(func.date(Activity.start) >= start_date)
        .where(func.date(Activity.start) <= end_date)
        .group_by(func.date(Activity.start))
    )
    _raw_data = session.exec(stmt).all()
    raw_data = {}
    for _date, _count, _duration in _raw_data:
        raw_data[_date] = {
            "activity_count": _count,
            "duration_seconds": round(_duration.total_seconds()) if _duration else 0,
        }
    _date = start_date
    grid_week_days: list[list[GridDay | None]] = []
    total_count, max_count = 0, 0
    total_duration_seconds, max_duration_seconds = 0, 0
    activity_days = 0
    while _date <= end_date:
        if _date.isoweekday() == 1:
            grid_week_days.append([])
        if _date > today:
            grid_week_days[-1].append(None)
        else:
            _data = raw_data.get(_date, {"activity_count": 0, "duration_seconds": 0})
            total_count += _data["activity_count"]
            total_duration_seconds += _data["duration_seconds"]
            max_count = max(max_count, _data["activity_count"])
            if _data["activity_count"] > 0:
                activity_days += 1
            max_duration_seconds = max(max_duration_seconds, _data["duration_seconds"])
            grid_week_days[-1].append(
                GridDay(
                    date=_date,
                    activity_count=_data["activity_count"],
                    duration_seconds=_data["duration_seconds"],
                )
            )
        _date += timedelta(days=1)

    grid_weeks = []
    months_found = set()
    for week in grid_week_days:
        start_date = week[0].date if week[0] is not None else None
        first_day = week[0]
        if first_day is None:
            continue
        label = None
        months_in_week = set(d.date.month for d in week if d is not None)
        if (
            len(months_in_week) == 1
            and months_in_week not in months_found
            and first_day.date.day <= 7
        ):
            label = months_in_week.pop()
            months_found.add(label)
        grid_weeks.append(
            GridWeek(
                start_date=first_day.date,
                month=label,
                days=week,
            )
        )

    _query_params = {"user_id": _user_id, "as_of_date": datetime.now().date()}
    _week_streak = _run_query(session, "activity_streak_weeks.sql", _query_params)[0]
    _activities_this_month = _run_query(
        session, "activities_this_month.sql", _query_params
    )[0]
    _last_active_day = _run_query(session, "last_activity_date.sql", _query_params)[0]

    return ActivityGridResponse(
        weeks=grid_weeks,
        scale_max=GridMax(
            activity_count=max_count,
            duration_seconds=max_duration_seconds,
        ),
        totals=GridTotals(
            activity_count=total_count,
            duration_seconds=total_duration_seconds,
            active_days=activity_days,
        ),
        summary=GridSummary(
            activities_this_month=_activities_this_month,
            last_active_day=_last_active_day,
            week_activity_streak=_week_streak,
        ),
    )
