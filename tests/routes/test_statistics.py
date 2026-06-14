from datetime import date

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from verve_backend.api.routes.statistics import (
    ActivityGridResponse,
    GridWeek,
    _find_grid_start_end,
)


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
                            }
                        ],
                    }
                ],
                "scale_max": {"activity_count": 1, "duration_seconds": 60},
                "totals": {
                    "active_days": 1,
                    "activity_count": 1,
                    "duration_seconds": 60,
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
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-07",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            {
                                "date": "2024-01-08",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                        ],
                    }
                ],
                "scale_max": {"activity_count": 1, "duration_seconds": 60},
                "totals": {
                    "active_days": 1,
                    "activity_count": 1,
                    "duration_seconds": 60,
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
                            },
                            None,
                            None,
                            None,
                            {
                                "date": "2024-01-05",
                                "activity_count": 1,
                                "duration_seconds": 60,
                            },
                            None,
                            None,
                        ],
                    }
                ],
                "scale_max": {"activity_count": 2, "duration_seconds": 120},
                "totals": {
                    "active_days": 2,
                    "activity_count": 2,
                    "duration_seconds": 120,
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
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 0,
                                "duration_seconds": 0,
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
                "scale_max": {"activity_count": 0, "duration_seconds": 0},
                "totals": {
                    "active_days": 0,
                    "activity_count": 0,
                    "duration_seconds": 0,
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
                            },
                            {
                                "date": "2024-01-02",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-03",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-04",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-05",
                                "activity_count": 0,
                                "duration_seconds": 0,
                            },
                            {
                                "date": "2024-01-06",
                                "activity_count": 0,
                                "duration_seconds": 0,
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
                "scale_max": {"activity_count": 0, "duration_seconds": 0},
                "totals": {
                    "active_days": 0,
                    "activity_count": 0,
                    "duration_seconds": 0,
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
        start, end = _find_grid_start_end(weeks)

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
    assert _response.weeks[-1].days[-1] is None
