from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.models import GoalCreate
from verve_backend.result import ErrorType


def _validate_type_aggregation_combination(
    goal: GoalCreate,
) -> tuple[str, ErrorType] | None:
    match goal.type:
        case GoalType.LOCATION:
            if goal.aggregation != GoalAggregation.COUNT:
                return (
                    "Invalid combination: Location goal only support count aggregation",
                    ErrorType.VALIDATION,
                )
        case GoalType.MANUAL:
            if goal.aggregation not in [
                GoalAggregation.COUNT,
                GoalAggregation.DURATION,
            ]:
                return (
                    "Invalid combination: Manual goal only support count and "
                    "duration aggregation",
                    ErrorType.VALIDATION,
                )

        case GoalType.ACTIVITY:
            pass
        case _:
            raise NotImplementedError(f"{goal.type} is not supported")


def _validate_temporal_setup(goal: GoalCreate) -> tuple[str, ErrorType] | None:
    if goal.temporal_type == TemportalType.YEARLY and goal.month is not None:
        return (
            "Invalid combination: Yearly goals should not have month set",
            ErrorType.VALIDATION,
        )
    if goal.temporal_type == TemportalType.MONTHLY and goal.month is None:
        return (
            "Invalid combination: Monthly goals must have month set",
            ErrorType.VALIDATION,
        )


def validate_goal_creation(
    goal: GoalCreate,
) -> tuple[str, ErrorType] | None:
    """
    Validate goal creation data.

    Returns:
        None if validation passes, otherwise a tuple of error message and error type.
    """
    result = _validate_type_aggregation_combination(goal)
    if result:
        return result

    result = _validate_temporal_setup(goal)
    if result:
        return result

    return None
