from datetime import date, datetime, timedelta

import pytest

from verve_backend.models import ActivityBase
from verve_backend.transformations import build_calendar_response


def test_activities_to_calendar_weeks() -> None:
    grid = [
        [
            date(2025, 11, 3),
            date(2025, 11, 4),
            date(2025, 11, 5),
            date(2025, 11, 6),
            date(2025, 11, 7),
            date(2025, 11, 8),
            date(2025, 11, 9),
        ]
    ]

    activities = [
        # 1 activitiy from 1 type on a day
        ActivityBase(
            name="1 1",
            start=datetime(2025, 11, 3, 12),
            duration=timedelta(minutes=1),
            distance=1.0,
            type_id=1,
            sub_type_id=1,
        ),
        # 2 activities from 1 type on a day
        ActivityBase(
            name="2 1",
            start=datetime(2025, 11, 4, 12),
            duration=timedelta(minutes=2),
            distance=2.0,
            type_id=1,
            sub_type_id=1,
        ),
        ActivityBase(
            name="2 2",
            start=datetime(2025, 11, 4, 12),
            duration=timedelta(minutes=5),
            distance=5.0,
            type_id=1,
            sub_type_id=2,
        ),
        # 2 activities from 2 type on a day
        ActivityBase(
            name="3 1",
            start=datetime(2025, 11, 5, 12),
            duration=timedelta(minutes=7),
            distance=7.0,
            type_id=1,
            sub_type_id=1,
        ),
        ActivityBase(
            name="3 2",
            start=datetime(2025, 11, 5, 12),
            duration=timedelta(minutes=9),
            distance=9.0,
            type_id=2,
            sub_type_id=None,
        ),
    ]

    activity_weeks = build_calendar_response(activities, grid, 11)
    assert len(activity_weeks) == 1

    week = activity_weeks[0]
    days = week.days

    # --- 1. Validate Week Aggregation ---
    # Total Distance: 1 + 2 + 5 + 7 + 9 = 24.0
    # Total Duration: 1 + 2 + 5 + 7 + 9 = 24 minutes = 1440 seconds
    assert week.week_summary.distance == pytest.approx(24.0)
    assert week.week_summary.duration == 1440
    assert week.week_summary.count == 5

    # --- 2. Validate Day 1 (Single Activity) ---
    day_1 = days[0]
    assert day_1.date == date(2025, 11, 3)
    assert day_1.active_type_ids == [1]

    # Day Totals
    assert day_1.total.distance == pytest.approx(1.0)
    assert day_1.total.duration == 60

    # Type 1 Specifics
    assert 1 in day_1.activities
    assert day_1.activities[1].distance == pytest.approx(1.0)
    assert day_1.activities[1].by_subtype[1].distance == pytest.approx(1.0)

    # --- 3. Validate Day 2 (Aggregation of same Type, different Subtypes) ---
    day_2 = days[1]
    assert day_2.date == date(2025, 11, 4)
    assert day_2.active_type_ids == [1]  # Only one main type, even though 2 activities

    # Day Totals (2.0 + 5.0)
    assert day_2.total.distance == pytest.approx(7.0)
    assert day_2.total.duration == 420  # 2min + 5min

    # Type 1 Totals
    type_1_stats = day_2.activities[1]
    assert type_1_stats.distance == pytest.approx(7.0)

    # Subtype Breakdowns
    assert type_1_stats.by_subtype[1].distance == pytest.approx(2.0)  # Subtype 1
    assert type_1_stats.by_subtype[2].distance == pytest.approx(5.0)  # Subtype 2

    # --- 4. Validate Day 3 (Multiple Types) ---
    day_3 = days[2]
    assert day_3.date == date(2025, 11, 5)
    # Should list both types sorted
    assert day_3.active_type_ids == [1, 2]

    # Day Totals (7.0 + 9.0)
    assert day_3.total.distance == pytest.approx(16.0)

    # Type 1 Check
    assert day_3.activities[1].distance == pytest.approx(7.0)

    # Type 2 Check (Subtype None)
    assert 2 in day_3.activities
    assert day_3.activities[2].distance == pytest.approx(9.0)
    # Assuming logic maps None -> 0 for dictionary key
    assert day_3.activities[2].by_subtype[0].distance == pytest.approx(9.0)

    # --- 5. Validate Empty Day ---
    day_4 = days[3]
    assert day_4.date == date(2025, 11, 6)
    assert day_4.active_type_ids == []
    assert day_4.total.distance == 0.0
    assert day_4.total.duration == 0
    assert day_4.activities == {}
