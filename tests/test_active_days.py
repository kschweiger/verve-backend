from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.goal import update_goal_state
from verve_backend.models import Activity, Goal


@pytest.mark.parametrize(
    ("period", "month", "week"),
    [("yearly", None, None), ("monthly", 5, None), ("weekly", None, 18)],
)
def test_active_days_recalculates_after_activity_changes(
    db: Session, temp_user_id: UUID, period: str, month: int | None, week: int | None
) -> None:
    activities = [
        Activity(
            user_id=temp_user_id,
            name=name,
            timezone="America/Los_Angeles",
            start=datetime(2025, 5, day, hour, tzinfo=UTC),
            distance=None,
            duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=None,
        )
        for name, day, hour in [
            ("Cardio", 1, 8),
            ("Weights", 1, 18),
            ("Next day", 2, 8),
        ]
    ]
    goal = Goal(
        user_id=temp_user_id,
        name="Active days",
        target=2,
        year=2025,
        month=month,
        week=week,
        temporal_type=period,
        type="activity",
        aggregation="active_days",
    )
    db.add_all([*activities, goal])
    db.commit()

    def refresh() -> float:
        update_goal_state(
            session=db,
            user_id=temp_user_id,
            goal=goal,
            timezone=ZoneInfo("Europe/Berlin"),
        )
        db.refresh(goal)
        return goal.current

    assert refresh() == 2
    assert refresh() == 2
    same_day = Activity(
        user_id=temp_user_id,
        name="Another same-day workout",
        timezone="Europe/Berlin",
        start=datetime(2025, 5, 1, 19, tzinfo=UTC),
        distance=None,
        duration=timedelta(minutes=10),
        type_id=1,
        sub_type_id=None,
    )
    db.add(same_day)
    db.commit()
    assert refresh() == 2
    activities[2].start = datetime(2025, 5, 1, 20, tzinfo=UTC)
    db.add(activities[2])
    db.commit()
    assert refresh() == 1
    late = Activity(
        user_id=temp_user_id,
        name="Late upload",
        timezone="Europe/Berlin",
        start=datetime(2025, 5, 3, 8, tzinfo=UTC),
        distance=None,
        duration=timedelta(minutes=10),
        type_id=1,
        sub_type_id=None,
    )
    db.add(late)
    db.commit()
    assert refresh() == 2
    for activity in [*activities, same_day, late]:
        db.delete(activity)
    db.commit()
    assert refresh() == 0


@pytest.mark.parametrize(
    ("goal_type", "status"), [("activity", 200), ("manual", 422), ("location", 422)]
)
@pytest.mark.parametrize(
    ("period", "month", "week"),
    [("yearly", None, None), ("monthly", 5, None), ("weekly", None, 18)],
)
def test_active_days_api(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
    goal_type: str,
    status: int,
    period: str,
    month: int | None,
    week: int | None,
    user1_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.put(
        "/goal/",
        headers=headers,
        json={
            "temporal_type": period,
            "month": month,
            "week": week,
            "name": "Active days",
            "type": goal_type,
            "aggregation": "active_days",
            "target": 2,
            "year": 2025,
        },
    )
    assert response.status_code == status
    if status != 200:
        return
    goal_id = response.json()["data"][0]["id"]
    for day, expected in [(1, 0.5), (2, 1), (3, 1.5)]:
        db.add(
            Activity(
                user_id=temp_user_id,
                name="Workout",
                timezone="Europe/Berlin",
                start=datetime(2025, 5, day, 8, tzinfo=UTC),
                distance=None,
                duration=timedelta(minutes=30),
                type_id=1,
                sub_type_id=None,
            )
        )
        db.commit()
        response = client.get("/goal/", headers=headers, params={"year": 2025})
        assert response.status_code == 200
        goal = next(g for g in response.json()["data"] if g["id"] == goal_id)
        assert goal["current"] == day
        assert goal["aggregation"] == "active_days"
        assert goal["progress"] == expected
        assert goal["reached"] is (day >= 2)

    response = client.get(
        "/goal/",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"year": 2025},
    )
    assert response.status_code == 200
    assert goal_id not in {goal["id"] for goal in response.json()["data"]}


@pytest.mark.parametrize(
    ("zone", "expected"), [("Europe/Berlin", 2), ("America/Los_Angeles", 1)]
)
def test_active_days_uses_user_calendar(
    db: Session, temp_user_id: UUID, zone: str, expected: int
) -> None:
    for hour in [20, 23]:
        db.add(
            Activity(
                user_id=temp_user_id,
                name="Workout",
                timezone="UTC",
                start=datetime(2025, 5, 1, hour, tzinfo=UTC),
                distance=None,
                duration=timedelta(hours=4),
                type_id=1,
                sub_type_id=None,
            )
        )
    goal = Goal(
        user_id=temp_user_id,
        name="Calendar",
        target=3,
        year=2025,
        type="activity",
        aggregation="active_days",
    )
    db.add(goal)
    db.commit()
    update_goal_state(
        session=db, user_id=temp_user_id, goal=goal, timezone=ZoneInfo(zone)
    )
    assert goal.current == expected


@pytest.mark.parametrize(
    ("period", "month", "week"),
    [("yearly", None, None), ("monthly", 3, None), ("weekly", None, 14)],
)
def test_active_days_period_boundaries(
    db: Session, temp_user_id: UUID, period: str, month: int | None, week: int | None
) -> None:
    bounds = {
        "yearly": (
            datetime(2024, 12, 31, 23, tzinfo=UTC),
            datetime(2025, 12, 31, 23, tzinfo=UTC),
        ),
        "monthly": (
            datetime(2025, 2, 28, 23, tzinfo=UTC),
            datetime(2025, 3, 31, 22, tzinfo=UTC),
        ),
        "weekly": (
            datetime(2025, 3, 30, 22, tzinfo=UTC),
            datetime(2025, 4, 6, 22, tzinfo=UTC),
        ),
    }
    start, end = bounds[period]
    for instant in [
        start - timedelta(seconds=1),
        start,
        end - timedelta(seconds=1),
        end,
    ]:
        db.add(
            Activity(
                user_id=temp_user_id,
                name="Boundary",
                timezone="UTC",
                start=instant,
                distance=None,
                duration=timedelta(minutes=30),
                type_id=1,
                sub_type_id=None,
            )
        )
    goal = Goal(
        user_id=temp_user_id,
        name="Boundary",
        target=3,
        year=2025,
        month=month,
        week=week,
        temporal_type=period,
        type="activity",
        aggregation="active_days",
    )
    db.add(goal)
    db.commit()
    update_goal_state(
        session=db, user_id=temp_user_id, goal=goal, timezone=ZoneInfo("Europe/Berlin")
    )
    assert goal.current == 2


@pytest.mark.parametrize(
    ("instants", "week"),
    [
        pytest.param(
            [
                datetime(2025, 10, 26, 0, 30, tzinfo=UTC),
                datetime(2025, 10, 26, 1, 30, tzinfo=UTC),
            ],
            None,
            id="repeated-dst-hour",
        ),
        pytest.param(
            [
                datetime(2025, 3, 30, 0, 30, tzinfo=UTC),
                datetime(2025, 3, 30, 1, 30, tzinfo=UTC),
            ],
            None,
            id="spring-dst-day",
        ),
        pytest.param(
            [
                datetime(2024, 12, 30, 8, tzinfo=UTC),
                datetime(2024, 12, 30, 18, tzinfo=UTC),
            ],
            1,
            id="iso-week-in-previous-year",
        ),
    ],
)
def test_active_days_calendar_edge_cases(
    db: Session,
    temp_user_id: UUID,
    user1_id: UUID,
    instants: list[datetime],
    week: int | None,
) -> None:
    for instant in instants:
        db.add(
            Activity(
                user_id=temp_user_id,
                name="Workout",
                timezone="UTC",
                start=instant,
                distance=None,
                duration=timedelta(minutes=30),
                type_id=1,
                sub_type_id=None,
            )
        )
    db.add(
        Activity(
            user_id=user1_id,
            name="Other user",
            timezone="UTC",
            start=instants[0] + timedelta(days=1),
            distance=None,
            duration=timedelta(minutes=30),
            type_id=1,
            sub_type_id=None,
        )
    )
    goal = Goal(
        user_id=temp_user_id,
        name="Calendar edge",
        target=3,
        year=2025,
        week=week,
        temporal_type="weekly" if week else "yearly",
        type="activity",
        aggregation="active_days",
    )
    db.add(goal)
    db.commit()
    update_goal_state(
        session=db, user_id=temp_user_id, goal=goal, timezone=ZoneInfo("Europe/Berlin")
    )
    assert goal.current == 1
