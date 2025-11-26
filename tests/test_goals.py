import pytest

from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.goal import (
    _validate_temporal_setup,
    _validate_type_aggregation_combination,
)
from verve_backend.models import GoalCreate


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
