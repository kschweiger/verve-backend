import logging
from uuid import UUID

from sqlmodel import Session, col, func, select

from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.models import Activity, Goal, GoalCreate
from verve_backend.result import ErrorType

logger = logging.getLogger("uvicorn.error")


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


def update_goal_state(*, session: Session, user_id: UUID, goal: Goal) -> None:
    if goal.type == GoalType.MANUAL:
        # Manual goals are updated manually, so we don't update them here
        return
    elif goal.type == GoalType.LOCATION:
        # TODO: Location not implemented yet
        return
    else:
        last_updated = goal.current_updated
        stmt = (
            select(Activity)
            .where(func.extract("year", col(Activity.start)) == goal.year)
            .where(Activity.user_id == user_id)
        )
        if goal.month is not None:
            stmt = stmt.where(func.extract("month", col(Activity.start)) == goal.month)
        last_updated_added = False
        if (
            last_updated is not None
            and goal.aggregation != GoalAggregation.AVG_DISTANCE
        ):
            last_updated_added = True
            stmt = stmt.where(col(Activity.created_at) > last_updated)
        activities = session.exec(stmt).all()
        if len(activities) == 0:
            logger.debug("No new activities found for goal update")
            return
        if goal.aggregation == GoalAggregation.COUNT:
            goal.current += len(activities)
        elif goal.aggregation == GoalAggregation.DURATION:
            goal.current += sum(a.duration.total_seconds() for a in activities)
        elif goal.aggregation == GoalAggregation.TOTAL_DISTANCE:
            goal.current += sum(a.distance for a in activities)
        elif goal.aggregation == GoalAggregation.AVG_DISTANCE:
            assert not last_updated_added, "AVG_DISTANCE cannot be incremental"
            goal.current = sum(a.distance for a in activities) / len(activities)
        elif goal.aggregation == GoalAggregation.MAX_DISTANCE:
            goal.current = max(goal.current, max((a.distance for a in activities)))
        else:
            raise NotImplementedError(f"Aggregation {goal.aggregation} not implemented")

        session.add(goal)
        session.commit()
