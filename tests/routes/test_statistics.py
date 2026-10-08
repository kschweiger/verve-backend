from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlmodel import Session

from verve_backend.api.routes.statistics import (
    ActivityGridResponse,
    GridWeek,
    WeekStatsResponse,
    YearStatsResponse,
    _find_grid_start_end,
)
from verve_backend.models import Activity


def test_year_stats_filters_by_user_local_year(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.patch(
        "/users/me/timezone",
        headers=headers,
        params={"timezone_name": "America/Los_Angeles"},
    )
    assert response.status_code == 200

    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=start,
            duration=timedelta(minutes=30),
            distance=1.0,
            moving_duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=1,
            name="Year boundary",
            user_id=temp_user_id,
        )
        for start in (
            datetime(2025, 1, 1, 7, 30, tzinfo=UTC),
            datetime(2025, 1, 1, 8, 30, tzinfo=UTC),
        )
    )
    db.commit()

    for params, expected_count in [
        ({"year": 2024}, 1),
        ({"year": 2025}, 1),
        ({}, 2),
    ]:
        response = client.get("/statistics/year", headers=headers, params=params)
        assert response.status_code == 200
        stats = YearStatsResponse.model_validate(response.json())
        assert stats.count.total == expected_count
        assert stats.count.per_sub_type[1][1] == expected_count


def test_week_stats_rejects_invalid_iso_week(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    db.add(
        Activity(
            timezone="Europe/Berlin",
            start=datetime(2025, 12, 29, 12, tzinfo=UTC),
            duration=timedelta(minutes=30),
            moving_duration=timedelta(minutes=30),
            distance=1.0,
            type_id=1,
            sub_type_id=1,
            name="Adjacent ISO year",
            user_id=temp_user_id,
        )
    )
    db.commit()
    response = client.get(
        "/statistics/week",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"year": 2025, "week": 53, "activity_type_id": 1},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid ISO week/year combination"


@pytest.mark.parametrize(
    ("year", "week"),
    [
        pytest.param(10000, 1, id="unrepresentable-year"),
        pytest.param(9999, 52, id="unrepresentable-exclusive-end"),
    ],
)
def test_week_stats_rejects_unrepresentable_range(
    client: TestClient, temp_user_token: str, year: int, week: int
) -> None:
    response = client.get(
        "/statistics/week",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"year": year, "week": week, "activity_type_id": 1},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid ISO week/year combination"


@pytest.mark.parametrize(
    ("params", "status_code"),
    [
        pytest.param({"year": 2025}, 400, id="year-only"),
        pytest.param({"week": 1}, 400, id="week-only"),
        pytest.param({"year": 2025, "week": 0}, 422, id="week-below-range"),
        pytest.param({"year": 2025, "week": 54}, 422, id="week-above-range"),
        pytest.param({"year": "invalid", "week": 1}, 422, id="malformed-year"),
        pytest.param({"year": 2025, "week": "invalid"}, 422, id="malformed-week"),
    ],
)
def test_week_stats_parameter_validation(
    client: TestClient, temp_user_token: str, params: dict, status_code: int
) -> None:
    response = client.get(
        "/statistics/week",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={**params, "activity_type_id": 1},
    )
    assert response.status_code == status_code
    if status_code == 400:
        assert response.json()["detail"] == "Both year and week must be set."
    else:
        assert response.json()["detail"][0]["loc"] == [
            "query",
            "year" if params.get("year") == "invalid" else "week",
        ]


@pytest.mark.parametrize(
    ("year", "week", "monday", "sunday"),
    [
        pytest.param(2020, 53, date(2020, 12, 28), date(2021, 1, 3), id="week-53"),
        pytest.param(2025, 1, date(2024, 12, 30), date(2025, 1, 5), id="week-1"),
    ],
)
def test_week_stats_accepts_iso_year_boundary_weeks(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
    year: int,
    week: int,
    monday: date,
    sunday: date,
) -> None:
    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=datetime(
                day.year, day.month, day.day, 12, tzinfo=ZoneInfo("Europe/Berlin")
            ),
            duration=timedelta(minutes=30),
            moving_duration=timedelta(minutes=30),
            distance=1.0,
            type_id=1,
            sub_type_id=1,
            name="ISO year boundary",
            user_id=temp_user_id,
        )
        for day in (monday, sunday)
    )
    db.commit()
    response = client.get(
        "/statistics/week",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"year": year, "week": week, "activity_type_id": 1},
    )
    assert response.status_code == 200
    stats = WeekStatsResponse.model_validate(response.json())
    assert stats.distance.total == 2.0
    assert stats.distance.per_day[monday] == 1.0
    assert stats.distance.per_day[sunday] == 1.0


def test_week_stats_uses_half_open_local_bounds(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=datetime.fromisoformat(start),
            duration=timedelta(minutes=30),
            moving_duration=timedelta(minutes=30),
            distance=1.0,
            type_id=1,
            sub_type_id=1,
            name="DST week boundary",
            user_id=temp_user_id,
        )
        for start in (
            "2026-03-22T22:59:59Z",
            "2026-03-22T23:00:00Z",
            "2026-03-29T21:59:59Z",
            "2026-03-29T22:00:00Z",
        )
    )
    db.commit()
    response = client.get(
        "/statistics/week",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"year": 2026, "week": 13, "activity_type_id": 1},
    )
    assert response.status_code == 200
    stats = WeekStatsResponse.model_validate(response.json())
    assert stats.distance.total == 2.0
    assert stats.distance.per_day[date(2026, 3, 23)] == 1.0
    assert stats.distance.per_day[date(2026, 3, 29)] == 1.0


def test_week_stats_uses_user_local_week_and_dates(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.patch(
        "/users/me/timezone",
        headers=headers,
        params={"timezone_name": "America/Los_Angeles"},
    )
    assert response.status_code == 200

    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=start,
            duration=timedelta(minutes=30),
            distance=1.0,
            moving_duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=1,
            name="Week boundary",
            user_id=temp_user_id,
        )
        for start in (
            datetime(2025, 1, 6, 7, 30, tzinfo=UTC),
            datetime(2025, 1, 6, 8, 30, tzinfo=UTC),
        )
    )
    db.commit()

    with freeze_time("2025-01-06 01:00:00"):
        response = client.get(
            "/statistics/week", headers=headers, params={"activity_type_id": 1}
        )
    assert response.status_code == 200
    week = WeekStatsResponse.model_validate(response.json())
    assert week.distance.total == 1.0
    assert week.distance.per_day[date(2025, 1, 5)] == 1.0

    response = client.get(
        "/statistics/week",
        headers=headers,
        params={"year": 2025, "week": 2, "activity_type_id": 1},
    )
    assert response.status_code == 200
    week = WeekStatsResponse.model_validate(response.json())
    assert week.distance.total == 1.0
    assert week.distance.per_day[date(2025, 1, 6)] == 1.0


def test_calendar_uses_user_local_month_and_dates(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.patch(
        "/users/me/timezone",
        headers=headers,
        params={"timezone_name": "America/Los_Angeles"},
    )
    assert response.status_code == 200

    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=start,
            duration=timedelta(minutes=30),
            distance=1.0,
            moving_duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=1,
            name=name,
            user_id=temp_user_id,
        )
        for name, start in (
            ("December", datetime(2025, 1, 1, 7, 30, tzinfo=UTC)),
            ("January", datetime(2025, 1, 1, 8, 30, tzinfo=UTC)),
        )
    )
    db.commit()

    with freeze_time("2025-01-01 01:00:00"):
        response = client.get("/statistics/calender", headers=headers)
    assert response.status_code == 200
    calendar = response.json()
    assert (calendar["year"], calendar["month"]) == (2024, 12)

    response = client.get(
        "/statistics/calender", headers=headers, params={"year": 2025, "month": 1}
    )
    assert response.status_code == 200
    days = {
        day["date"]: day for week in response.json()["weeks"] for day in week["days"]
    }
    assert [item["name"] for item in days["2024-12-31"]["items"]] == ["December"]
    assert [item["name"] for item in days["2025-01-01"]["items"]] == ["January"]


def test_activity_grid_uses_user_local_dates(
    db: Session, client: TestClient, temp_user_token: str, temp_user_id: UUID
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.patch(
        "/users/me/timezone",
        headers=headers,
        params={"timezone_name": "America/Los_Angeles"},
    )
    assert response.status_code == 200

    db.add_all(
        Activity(
            timezone="Europe/Berlin",
            start=start,
            duration=timedelta(minutes=30),
            distance=1.0,
            moving_duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=1,
            name=name,
            user_id=temp_user_id,
        )
        for name, start in (
            ("Previous week", datetime(2025, 1, 27, 7, 30, tzinfo=UTC)),
            ("Current week", datetime(2025, 2, 1, 0, 30, tzinfo=UTC)),
        )
    )
    db.commit()

    with freeze_time("2025-02-01 01:00:00"):
        response = client.get(
            "/statistics/activity-grid", headers=headers, params={"weeks": 1}
        )
    assert response.status_code == 200
    grid = ActivityGridResponse.model_validate(response.json())
    days = {day.date: day for week in grid.weeks for day in week.days if day}
    assert days[date(2025, 1, 26)].activity_count == 1
    assert days[date(2025, 1, 31)].activity_count == 1
    assert grid.totals.activity_count == 2
    assert grid.summary.activities_this_month == 2
    assert grid.summary.week_activity_streak == 2
    assert grid.summary.last_active_day == date(2025, 1, 31)


def test_duration_stat_responses_use_effective_duration_name() -> None:
    year = YearStatsResponse.model_validate(
        {
            "distance": {
                "total": 1.0,
                "per_type": {1: 1.0},
                "per_sub_type": {1: {1: 1.0}},
            },
            "duration": {
                "total": 120,
                "per_type": {1: 120},
                "per_sub_type": {1: {1: 120}},
            },
            "effective_duration": {
                "total": 90,
                "per_type": {1: 90},
                "per_sub_type": {1: {1: 90}},
            },
            "count": {"total": 1, "per_type": {1: 1}, "per_sub_type": {1: {1: 1}}},
        }
    )
    week = WeekStatsResponse.model_validate(
        {
            "distance": {
                "per_day": {"2024-01-01": 1.0},
                "pie_data": {1: 1.0},
                "total": 1.0,
            },
            "elevation_gain": {
                "per_day": {"2024-01-01": None},
                "pie_data": {},
                "total": 0.0,
            },
            "duration": {
                "per_day": {"2024-01-01": 120},
                "pie_data": {1: 120.0},
                "total": 120,
            },
            "effective_duration": {
                "per_day": {"2024-01-01": 90},
                "pie_data": {1: 90.0},
                "total": 90,
            },
        }
    )

    year_dump = year.model_dump()
    week_dump = week.model_dump()
    assert "effective_duration" in year_dump
    assert "moving_duration" not in year_dump
    assert "effective_duration" in week_dump
    assert "moving_duration" not in week_dump


@pytest.mark.parametrize(
    ("model", "match_exp"),
    [
        # No days
        (
            {
                "weeks": [],
                "scale_max": {"activity_count": 0, "duration_seconds": 0},
                "totals": {
                    "active_days": 0,
                    "activity_count": 0,
                    "duration_seconds": 0,
                    "effective_duration_seconds": 0,
                },
            },
            "List should have at least 1 item after validation",
        ),
        # Too few days
        (
            {
                "weeks": [
                    {
                        "start_date": "2024-01-01",
                        "month": 1,
                        "days": [
                            {
                                "date": "2024-01-01",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            }
                        ],
                    }
                ],
                "scale_max": {"activity_count": 1, "duration_seconds": 60},
                "totals": {
                    "active_days": 1,
                    "activity_count": 1,
                    "duration_seconds": 60,
                    "effective_duration_seconds": 60,
                },
            },
            "List should have at least 7 items after validation",
        ),
        # Too many days
        (
            {
                "weeks": [
                    {
                        "start_date": "2024-01-01",
                        "month": 1,
                        "days": [
                            {
                                "date": "2024-01-01",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-07",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-08",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                        ],
                    }
                ],
                "scale_max": {
                    "activity_count": 1,
                    "duration_seconds": 60,
                    "effective_duration_seconds": 60,
                },
                "totals": {
                    "active_days": 1,
                    "activity_count": 1,
                    "duration_seconds": 60,
                    "effective_duration_seconds": 60,
                },
            },
            "List should have at most 7 items after validation",
        ),
        # Intermediate Nones
        (
            {
                "weeks": [
                    {
                        "start_date": "2024-01-01",
                        "month": 1,
                        "days": [
                            {
                                "date": "2024-01-01",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            None,
                            None,
                            None,
                            {
                                "date": "2024-01-05",
                                "activity_count": 1,
                                "duration_seconds": 60,
                                "effective_duration_seconds": 60,
                            },
                            None,
                            None,
                        ],
                    }
                ],
                "scale_max": {
                    "activity_count": 2,
                    "duration_seconds": 120,
                    "effective_duration_seconds": 120,
                },
                "totals": {
                    "active_days": 2,
                    "activity_count": 2,
                    "duration_seconds": 120,
                    "effective_duration_seconds": 120,
                },
            },
            "None is only allowed as trailing values in last week",
        ),
        # Week misses a day
        (
            {
                "weeks": [
                    {
                        "start_date": "2024-01-01",
                        "month": 1,
                        "days": [
                            {
                                "date": "2024-01-01",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                        ],
                    },
                    {
                        "start_date": "2024-01-08",
                        "month": None,
                        "days": [
                            {
                                "date": "2024-01-08",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                        ],
                    },
                ],
                "scale_max": {
                    "activity_count": 0,
                    "duration_seconds": 0,
                    "effective_duration_seconds": 0,
                },
                "totals": {
                    "active_days": 0,
                    "activity_count": 0,
                    "duration_seconds": 0,
                    "effective_duration_seconds": 0,
                },
            },
            "List should have at least 7 items after validation",
        ),
        # None in full week
        (
            {
                "weeks": [
                    {
                        "start_date": "2024-01-01",
                        "month": 1,
                        "days": [
                            {
                                "date": "2024-01-01",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            None,
                        ],
                    },
                    {
                        "start_date": "2024-01-08",
                        "month": None,
                        "days": [
                            {
                                "date": "2024-01-08",
                                "activity_count": 0,
                                "duration_seconds": 0,
                                "effective_duration_seconds": 0,
                            },
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                        ],
                    },
                ],
                "scale_max": {
                    "activity_count": 0,
                    "duration_seconds": 0,
                    "effective_duration_seconds": 0,
                },
                "totals": {
                    "active_days": 0,
                    "activity_count": 0,
                    "duration_seconds": 0,
                    "effective_duration_seconds": 0,
                },
            },
            "None is only allowed in last week",
        ),
    ],
)
def test_activity_grid_response_validation(model: dict, match_exp: str) -> None:
    with pytest.raises(ValueError, match=match_exp):
        ActivityGridResponse.model_validate(model)


@pytest.mark.parametrize(
    ("model", "match_exp"),
    [
        (
            {
                "start_date": "2024-01-01",
                "month": 2,
                "days": [
                    {
                        "date": "2024-01-01",
                        "activity_count": 0,
                        "duration_seconds": 0,
                        "effective_duration_seconds": 0,
                    },
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            },
            "First day of the week must match the month label",
        ),
        (
            {
                "start_date": "2024-01-01",
                "month": 1,
                "days": [
                    None,
                    {
                        "date": "2024-01-01",
                        "activity_count": 1,
                        "duration_seconds": 60,
                        "effective_duration_seconds": 60,
                    },
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            },
            "First day of the week cannot be None",
        ),
        (
            {
                "start_date": "2024-01-02",
                "month": None,
                "days": [
                    {
                        "date": "2024-01-01",
                        "activity_count": 1,
                        "duration_seconds": 60,
                        "effective_duration_seconds": 60,
                    },
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            },
            "Start date must match the date of the first day",
        ),
    ],
)
def test_activity_grid_week(model: dict, match_exp: str) -> None:
    with pytest.raises(ValueError, match=match_exp):
        GridWeek.model_validate(model)


@pytest.mark.parametrize(
    ("today", "weeks", "exp_start", "exp_end"),
    [
        ("2026-06-13", 0, date(2026, 6, 8), date(2026, 6, 14)),
        ("2026-06-13", 1, date(2026, 6, 1), date(2026, 6, 14)),
        ("2026-06-13", 53, date(2025, 6, 2), date(2026, 6, 14)),
    ],
)
def test_find_grid_start_end(
    today: str, weeks: int, exp_start: date, exp_end: date
) -> None:
    with freeze_time(today):
        start, end = _find_grid_start_end(weeks, ZoneInfo("Europe/Berlin"))

    assert start == exp_start
    assert end == exp_end

    assert start.isoweekday() == 1
    assert end.isoweekday() == 7


@freeze_time("2025-02-01")
def test_activity_grid_route(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.get(
        "/statistics/activity-grid",
        params={"weeks": 4},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == 200

    _response = ActivityGridResponse.model_validate(response.json())
    # 1.2.2025 was saturday. So last day of last week should be None
    print(_response.weeks[-1].days)
    print(_response.summary)
    assert _response.weeks[-1].days[-1] is None
    assert _response.summary.week_activity_streak == 1
    assert _response.summary.last_active_day == date(year=2025, month=2, day=1)
