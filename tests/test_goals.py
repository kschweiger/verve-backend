from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import Session

from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.goal import (
    _validate_temporal_setup,
    _validate_type_aggregation_combination,
    update_goal_state,
)
from verve_backend.models import Activity, Goal, GoalCreate


@pytest.mark.parametrize(
    ("temporal_type", "year", "month", "is_valid"),
    [
        (TemportalType.YEARLY, 2025, None, True),
        (TemportalType.YEARLY, 2025, 2, False),
        (TemportalType.MONTHLY, 2025, None, False),
        (TemportalType.MONTHLY, 2025, 2, True),
    ],
)
def test_temporal_validation(
    temporal_type: TemportalType,
    year: int,
    month: int | None,
    is_valid: bool,
) -> None:
    res = _validate_temporal_setup(
        GoalCreate(
            name="Some Name",
            target=10,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
            year=year,
            month=month,
            temporal_type=temporal_type,
        )
    )

    if is_valid:
        assert res is None
    else:
        assert isinstance(res, tuple)


@pytest.mark.parametrize(
    ("goal_type", "aggregation", "is_valid"),
    [
        # Location goal
        (GoalType.LOCATION, GoalAggregation.COUNT, True),
        (GoalType.LOCATION, GoalAggregation.DURATION, False),
        (GoalType.LOCATION, GoalAggregation.AVG_DISTANCE, False),
        (GoalType.LOCATION, GoalAggregation.TOTAL_DISTANCE, False),
        (GoalType.LOCATION, GoalAggregation.MAX_DISTANCE, False),
        # MANUAL goal
        (GoalType.MANUAL, GoalAggregation.COUNT, True),
        (GoalType.MANUAL, GoalAggregation.DURATION, True),
        (GoalType.MANUAL, GoalAggregation.AVG_DISTANCE, False),
        (GoalType.MANUAL, GoalAggregation.TOTAL_DISTANCE, False),
        (GoalType.MANUAL, GoalAggregation.MAX_DISTANCE, False),
        # ACTIVITY goal
        (GoalType.ACTIVITY, GoalAggregation.COUNT, True),
        (GoalType.ACTIVITY, GoalAggregation.DURATION, True),
        (GoalType.ACTIVITY, GoalAggregation.AVG_DISTANCE, True),
        (GoalType.ACTIVITY, GoalAggregation.TOTAL_DISTANCE, True),
        (GoalType.ACTIVITY, GoalAggregation.MAX_DISTANCE, True),
    ],
)
def test_type_aggregation_validation(
    goal_type: GoalType,
    aggregation: GoalAggregation,
    is_valid: bool,
) -> None:
    res = _validate_type_aggregation_combination(
        GoalCreate(
            name="Some Name",
            target=10,
            type=goal_type,
            aggregation=aggregation,
            year=2025,
        )
    )
    if is_valid:
        assert res is None
    else:
        assert isinstance(res, tuple)


@pytest.mark.parametrize(
    ("goal_month", "current_updated", "agg", "temporal_type", "exp_current_value"),
    [
        (5, None, GoalAggregation.TOTAL_DISTANCE, TemportalType.MONTHLY, 60),
        (None, None, GoalAggregation.TOTAL_DISTANCE, TemportalType.YEARLY, 100),
        (
            5,
            datetime(2025, 5, 1, 20),
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.MONTHLY,
            50,
        ),
        (5, None, GoalAggregation.MAX_DISTANCE, TemportalType.MONTHLY, 30),
        (5, None, GoalAggregation.COUNT, TemportalType.MONTHLY, 3),
        (None, None, GoalAggregation.COUNT, TemportalType.YEARLY, 4),
        (5, None, GoalAggregation.DURATION, TemportalType.MONTHLY, 60 * 60),
        (5, None, GoalAggregation.AVG_DISTANCE, TemportalType.MONTHLY, 60 / 3),
        (None, None, GoalAggregation.MAX_DISTANCE, TemportalType.YEARLY, 40),
    ],
)
def test_update_activity_goal(
    db: Session,
    temp_user_id: UUID,
    goal_month: int | None,
    current_updated: datetime | None,
    agg: GoalAggregation,
    temporal_type: TemportalType,
    exp_current_value: float,
) -> None:
    activity_1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 1, 12),
        distance=10,
        duration=timedelta(minutes=10),
        type_id=1,
        sub_type_id=None,
        name="Activity 1",
        created_at=datetime(2025, 5, 1, 18),
    )
    activity_2 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 2, 12),
        distance=20,
        duration=timedelta(minutes=20),
        type_id=1,
        sub_type_id=None,
        name="Activity 2",
        created_at=datetime(2025, 5, 2, 18),
    )
    activity_3 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 3, 12),
        distance=30,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity 3",
        created_at=datetime(2025, 5, 3, 18),
    )
    activity_4 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 6, 1, 12),
        distance=40,
        duration=timedelta(minutes=40),
        type_id=1,
        sub_type_id=None,
        name="Activity 3",
        created_at=datetime(2025, 6, 1, 18),
    )
    goal = Goal(
        user_id=temp_user_id,
        name="Test Goal",
        target=100,
        temporal_type=temporal_type,
        year=2025,
        month=goal_month,
        type=GoalType.ACTIVITY,
        aggregation=agg,
        current=0,
        current_updated=current_updated,
    )
    db.add_all([activity_1, activity_2, activity_3, activity_4, goal])
    db.commit()
    db.refresh(goal)

    update_goal_state(session=db, user_id=temp_user_id, goal=goal)

    updated_goal = db.get(Goal, goal.id)
    assert updated_goal is not None
    assert updated_goal.current == exp_current_value
