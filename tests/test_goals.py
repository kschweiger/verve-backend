from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlmodel import Session

from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.goal import (
    GoalContraints,
    _validate_temporal_setup,
    _validate_type_aggregation_combination,
    update_goal_state,
    validate_constraints,
)
from verve_backend.models import Activity, Equipment, EquipmentType, Goal, GoalCreate


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
    (
        "goal_month",
        "current_updated",
        "agg",
        "temporal_type",
        "constraints",
        "exp_current_value",
    ),
    [
        (5, None, GoalAggregation.TOTAL_DISTANCE, TemportalType.MONTHLY, {}, 60),
        (None, None, GoalAggregation.TOTAL_DISTANCE, TemportalType.YEARLY, {}, 100),
        (
            5,
            datetime(2025, 5, 1, 20),
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.MONTHLY,
            {},
            50,
        ),
        (5, None, GoalAggregation.MAX_DISTANCE, TemportalType.MONTHLY, {}, 30),
        (5, None, GoalAggregation.COUNT, TemportalType.MONTHLY, {}, 3),
        (None, None, GoalAggregation.COUNT, TemportalType.YEARLY, {}, 4),
        (5, None, GoalAggregation.DURATION, TemportalType.MONTHLY, {}, 60 * 60),
        (5, None, GoalAggregation.AVG_DISTANCE, TemportalType.MONTHLY, {}, 60 / 3),
        (None, None, GoalAggregation.MAX_DISTANCE, TemportalType.YEARLY, {}, 40),
        # ----- Constraints -----
        (
            None,
            None,
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.YEARLY,
            {"type_id": 1},
            60,
        ),
        (
            None,
            None,
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.YEARLY,
            {"type_id": 3},
            0,
        ),
        (
            None,
            None,
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.YEARLY,
            {"type_id": 1, "sub_type_id": 1},
            50,
        ),
        (
            None,
            None,
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.YEARLY,
            {"equipment_ids": [0]},
            40,
        ),
        (
            None,
            None,
            GoalAggregation.TOTAL_DISTANCE,
            TemportalType.YEARLY,
            {"equipment_ids": [0, 1]},
            30,
        ),
    ],
)
def test_update_activity_goal(
    db: Session,
    temp_user_id: UUID,
    goal_month: int | None,
    current_updated: datetime | None,
    agg: GoalAggregation,
    temporal_type: TemportalType,
    constraints: dict,
    exp_current_value: float,
) -> None:
    # TODO: Add  two equipments such that we can test
    # 1. Give me all with one equipment -> Should give 2 activities
    # 2. Give me all with the combination --> Should give one
    # We also need to replace the indices in the constraints dict with
    # the actual uuid's since I only know them at runtime
    equipment_1 = Equipment(
        name="First Equipment",
        equipment_type=EquipmentType.BIKE,
        user_id=temp_user_id,
    )
    equipment_2 = Equipment(
        name="Second Equipment",
        equipment_type=EquipmentType.SHOES,
        user_id=temp_user_id,
    )
    db.add_all([equipment_1, equipment_2])
    db.commit()
    db.refresh(equipment_1)
    db.refresh(equipment_2)

    if "equipment_ids" in constraints:
        _rp = {
            0: str(equipment_1.id),
            1: str(equipment_2.id),
        }
        assert isinstance(constraints["equipment_ids"], list)
        constraints["equipment_ids"] = [_rp[i] for i in constraints["equipment_ids"]]

    activity_1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 1, 12),
        distance=10,
        duration=timedelta(minutes=10),
        type_id=1,
        sub_type_id=None,
        name="Activity 1",
        created_at=datetime(2025, 5, 1, 18),
        equipment=[equipment_1],
    )
    activity_2 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 2, 12),
        distance=20,
        duration=timedelta(minutes=20),
        type_id=1,
        sub_type_id=1,
        name="Activity 2",
        created_at=datetime(2025, 5, 2, 18),
    )
    activity_3 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 5, 3, 12),
        distance=30,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=1,
        name="Activity 3",
        created_at=datetime(2025, 5, 3, 18),
        equipment=[equipment_1, equipment_2],
    )
    activity_4 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 6, 1, 12),
        distance=40,
        duration=timedelta(minutes=40),
        type_id=2,
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
        constraints=constraints,
    )
    db.add_all([activity_1, activity_2, activity_3, activity_4, goal])
    db.commit()
    db.refresh(goal)

    update_goal_state(session=db, user_id=temp_user_id, goal=goal)

    updated_goal = db.get(Goal, goal.id)
    assert updated_goal is not None
    assert updated_goal.current == exp_current_value


@pytest.mark.parametrize(
    ("constraint_dict", "should_pass"),
    [
        ({}, True),
        ({"type_id": 1}, True),
        ({"type_id": 1, "sub_type_id": 1}, True),
        (
            {
                "type_id": 1,
                "sub_type_id": 1,
                "equipment_ids": ["51a7c843-977b-4c29-89dd-32286a361abf"],
            },
            True,
        ),
        ({"sub_type_id": 1}, False),
        ({"type_id": 99}, False),
        ({"type_id": 1, "sub_type_id": 8}, False),
        ({"type_id": 1, "sub_type_id": 87}, False),
        (
            {
                "type_id": 1,
                "sub_type_id": 1,
                "equipment_ids": ["51ed27d8-0710-4cf2-8fc9-c7ef6602da8f"],
            },
            False,
        ),
    ],
)
def test_validate_contraints(
    db: Session,
    temp_user_id: UUID,
    constraint_dict: dict[str, Any],
    should_pass: bool,
) -> None:
    equipment_id = "51a7c843-977b-4c29-89dd-32286a361abf"
    equipment = Equipment(
        name="Equipment",
        equipment_type=EquipmentType.SHOES,
        user_id=temp_user_id,
        id=UUID(equipment_id),
    )
    db.add_all([equipment])
    db.commit()

    res = validate_constraints(session=db, constraints=constraint_dict)
    if should_pass:
        assert isinstance(res, GoalContraints)
    else:
        assert isinstance(res, tuple)


@pytest.mark.parametrize(
    ("temporal_type", "year", "month", "week", "is_valid"),
    [
        # Valid weekly goals
        (TemportalType.WEEKLY, 2025, None, 3, True),
        (TemportalType.WEEKLY, 2025, None, 1, True),
        (TemportalType.WEEKLY, 2025, None, 52, True),
        (TemportalType.WEEKLY, 2025, None, 53, True),
        # Invalid: weekly with month set
        (TemportalType.WEEKLY, 2025, 5, 3, False),
        # Invalid: weekly without week
        (TemportalType.WEEKLY, 2025, None, None, False),
        # Invalid: weekly with invalid week (0)
        (TemportalType.WEEKLY, 2025, None, 0, False),
        # Invalid: weekly with invalid week (54)
        (TemportalType.WEEKLY, 2025, None, 54, False),
        # Invalid: weekly with invalid week (-1)
        (TemportalType.WEEKLY, 2025, None, -1, False),
        # YEARLY with week set
        (TemportalType.YEARLY, 2025, None, 3, False),
        # MONTHLY with week set
        (TemportalType.MONTHLY, 2025, 5, 3, False),
    ],
)
def test_temporal_validation_weekly(
    temporal_type: TemportalType,
    year: int,
    month: int | None,
    week: int | None,
    is_valid: bool,
) -> None:
    res = _validate_temporal_setup(
        GoalCreate(
            name="Some Name",
            target=10,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.COUNT,
            year=year,
            month=month,
            week=week,
            temporal_type=temporal_type,
        )
    )

    if is_valid:
        assert res is None
    else:
        assert isinstance(res, tuple)


@pytest.mark.parametrize(
    (
        "goal_week",
        "current_updated",
        "agg",
        "exp_current_value",
    ),
    [
        # Week 3 (Jan 13-19, 2025): activities on 1/14 and 1/15
        (3, None, GoalAggregation.TOTAL_DISTANCE, 40),
        (3, None, GoalAggregation.COUNT, 2),
        (3, None, GoalAggregation.DURATION, 60 * 60),  # 60 minutes total
        (3, None, GoalAggregation.AVG_DISTANCE, 20),  # (10+30)/2
        (3, None, GoalAggregation.MAX_DISTANCE, 30),
        # Week 1 (Dec 30, 2024 - Jan 5, 2025): activities on 1/2 and 1/3
        (1, None, GoalAggregation.TOTAL_DISTANCE, 50),
        (1, None, GoalAggregation.COUNT, 2),
        # Incremental update: only count activities created after current_updated
        (3, datetime(2025, 1, 14, 20), GoalAggregation.TOTAL_DISTANCE, 30),
        # Week 52 (no activities): should return 0
        (52, None, GoalAggregation.COUNT, 0),
    ],
)
def test_update_weekly_activity_goal(
    db: Session,
    temp_user_id: UUID,
    goal_week: int,
    current_updated: datetime | None,
    agg: GoalAggregation,
    exp_current_value: float,
) -> None:
    """Test weekly goal state updates with various aggregations."""
    # Week 3 activities: Jan 13-19, 2025 (Mon-Sun)
    activity_week3_1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 14, 12),  # Tuesday, week 3
        distance=10,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity Week 3 - 1",
        created_at=datetime(2025, 1, 14, 18),
    )
    activity_week3_2 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 15, 12),  # Wednesday, week 3
        distance=30,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity Week 3 - 2",
        created_at=datetime(2025, 1, 15, 18),
    )

    # Week 1 activities: Dec 30, 2024 - Jan 5, 2025 (includes Dec 30-31, 2024)
    activity_week1_1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 2, 12),  # Thursday, week 1
        distance=20,
        duration=timedelta(minutes=20),
        type_id=1,
        sub_type_id=None,
        name="Activity Week 1 - 1",
        created_at=datetime(2025, 1, 2, 18),
    )
    activity_week1_2 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 3, 12),  # Friday, week 1
        distance=30,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity Week 1 - 2",
        created_at=datetime(2025, 1, 3, 18),
    )

    # Activity in week 4 (should not be counted for weeks 1 or 3)
    activity_week4 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 21, 12),  # Tuesday, week 4
        distance=25,
        duration=timedelta(minutes=25),
        type_id=1,
        sub_type_id=None,
        name="Activity Week 4",
        created_at=datetime(2025, 1, 21, 18),
    )

    goal = Goal(
        user_id=temp_user_id,
        name="Weekly Goal",
        target=100,
        temporal_type=TemportalType.WEEKLY,
        year=2025,
        month=None,
        week=goal_week,
        type=GoalType.ACTIVITY,
        aggregation=agg,
        current=0,
        current_updated=current_updated,
        constraints={},
    )

    db.add_all(
        [
            activity_week3_1,
            activity_week3_2,
            activity_week1_1,
            activity_week1_2,
            activity_week4,
            goal,
        ]
    )
    db.commit()
    db.refresh(goal)

    update_goal_state(session=db, user_id=temp_user_id, goal=goal)

    updated_goal = db.get(Goal, goal.id)
    assert updated_goal is not None
    assert updated_goal.current == exp_current_value


def test_weekly_goal_year_boundary(
    db: Session,
    temp_user_id: UUID,
) -> None:
    """
    Test that week 1 of 2025 correctly includes activities from
    Dec 30-31, 2024 (which belong to ISO week 1 of 2025).
    """
    # Activity on Dec 30, 2024 (ISO week 1 of 2025)
    activity_dec30 = Activity(
        user_id=temp_user_id,
        start=datetime(2024, 12, 30, 12),
        distance=10,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity on Dec 30",
        created_at=datetime(2024, 12, 30, 18),
    )

    # Activity on Dec 31, 2024 (ISO week 1 of 2025)
    activity_dec31 = Activity(
        user_id=temp_user_id,
        start=datetime(2024, 12, 31, 12),
        distance=15,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity on Dec 31",
        created_at=datetime(2024, 12, 31, 18),
    )

    # Activity on Jan 1, 2025 (ISO week 1 of 2025)
    activity_jan1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 1, 12),
        distance=20,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity on Jan 1",
        created_at=datetime(2025, 1, 1, 18),
    )

    # Goal for week 1 of 2025
    goal = Goal(
        user_id=temp_user_id,
        name="Week 1 Goal",
        target=100,
        temporal_type=TemportalType.WEEKLY,
        year=2025,
        month=None,
        week=1,
        type=GoalType.ACTIVITY,
        aggregation=GoalAggregation.TOTAL_DISTANCE,
        current=0,
        constraints={},
    )

    db.add_all([activity_dec30, activity_dec31, activity_jan1, goal])
    db.commit()
    db.refresh(goal)

    update_goal_state(session=db, user_id=temp_user_id, goal=goal)

    updated_goal = db.get(Goal, goal.id)
    assert updated_goal is not None
    # Should include all three activities: 10 + 15 + 20 = 45
    assert updated_goal.current == 45


def test_weekly_goal_incremental_update(
    db: Session,
    temp_user_id: UUID,
) -> None:
    """
    Test that incremental updates work correctly for weekly goals
    (only new activities are counted, not activities from before current_updated).
    """
    # First activity created at 2025-01-14 18:00
    activity_1 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 14, 12),
        distance=20,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity 1",
        created_at=datetime(2025, 1, 14, 18),
    )

    # Second activity created at 2025-01-16 18:00 (after current_updated)
    activity_2 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 15, 12),
        distance=30,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity 2",
        created_at=datetime(2025, 1, 16, 18),
    )

    # Third activity created at 2025-01-20 18:00 (after current_updated)
    activity_3 = Activity(
        user_id=temp_user_id,
        start=datetime(2025, 1, 17, 12),
        distance=25,
        duration=timedelta(minutes=30),
        type_id=1,
        sub_type_id=None,
        name="Activity 3",
        created_at=datetime(2025, 1, 20, 18),
    )

    # Goal with current_updated = 2025-01-15 19:00
    # This means only activities created AFTER 2025-01-15 19:00 should be counted
    goal = Goal(
        user_id=temp_user_id,
        name="Weekly Goal",
        target=100,
        temporal_type=TemportalType.WEEKLY,
        year=2025,
        month=None,
        week=3,
        type=GoalType.ACTIVITY,
        aggregation=GoalAggregation.TOTAL_DISTANCE,
        current=0,
        current_updated=datetime(2025, 1, 15, 19),
        constraints={},
    )

    db.add_all([activity_1, activity_2, activity_3, goal])
    db.commit()
    db.refresh(goal)

    update_goal_state(session=db, user_id=temp_user_id, goal=goal)

    updated_goal = db.get(Goal, goal.id)
    assert updated_goal is not None
    # Only activity_2 and activity_3 should be counted: 30 + 25 = 55
    # activity_1 was created at 18:00 which is before current_updated (19:00)
    assert updated_goal.current == 55
