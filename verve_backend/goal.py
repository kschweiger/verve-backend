import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from verve_backend.core.date_utils import get_week_date_range
from verve_backend.core.timing import log_timing
from verve_backend.enums import GoalAggregation, GoalType, TemportalType
from verve_backend.models import (
    Activity,
    ActivityEquipment,
    ActivitySubType,
    ActivityType,
    Equipment,
    Goal,
    GoalCreate,
)
from verve_backend.result import ErrorType

logger = logging.getLogger(__name__)


class GoalContraints(BaseModel):
    type_id: int | None = None
    sub_type_id: int | None = None
    equipment_ids: list[UUID] | None = None


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
    if goal.temporal_type == TemportalType.YEARLY:
        if goal.month is not None:
            return (
                "Invalid combination: Yearly goals should not have month set",
                ErrorType.VALIDATION,
            )
        if goal.week is not None:
            return (
                "Invalid combination: Yearly goals should not have week set",
                ErrorType.VALIDATION,
            )
    elif goal.temporal_type == TemportalType.MONTHLY:
        if goal.month is None:
            return (
                "Invalid combination: Monthly goals must have month set",
                ErrorType.VALIDATION,
            )
        if goal.week is not None:
            return (
                "Invalid combination: Monthly goals should not have week set",
                ErrorType.VALIDATION,
            )
    elif goal.temporal_type == TemportalType.WEEKLY:
        if goal.week is None:
            return (
                "Invalid combination: Weekly goals must have week set",
                ErrorType.VALIDATION,
            )
        if goal.month is not None:
            return (
                "Invalid combination: Weekly goals should not have month set",
                ErrorType.VALIDATION,
            )
        if goal.week < 1 or goal.week > 53:
            return (
                "Invalid combination: Week must be between 1 and 53",
                ErrorType.VALIDATION,
            )
    return None


def validate_constraints(
    *, session: Session, constraints: dict[str, Any]
) -> GoalContraints | tuple[str, ErrorType]:
    try:
        contraints_obj = GoalContraints.model_validate(constraints)
    except ValueError as e:
        err_uuid = uuid4()
        logger.info("[%s] Error on constraints validation: %s", err_uuid, e)
        return (
            "Invalid constraints format. Error code: %s" % err_uuid,
            ErrorType.VALIDATION,
        )
    if contraints_obj.type_id:
        main_type = session.get(ActivityType, contraints_obj.type_id)
        if main_type is None:
            return (
                "Invalid constraints: ActivityType with id %s not found"
                % contraints_obj.type_id,
                ErrorType.VALIDATION,
            )
    if not contraints_obj.type_id and contraints_obj.sub_type_id:
        return (
            "Invalid constraints: sub_type_id provided without type_id",
            ErrorType.VALIDATION,
        )

    if contraints_obj.type_id and contraints_obj.sub_type_id:
        sub_type = session.get(ActivitySubType, contraints_obj.sub_type_id)
        if sub_type is None:
            return (
                "Invalid constraints: ActivitySubType with id %s" % sub_type,
                ErrorType.VALIDATION,
            )
        if contraints_obj.type_id != sub_type.type_id:
            return (
                "Invalid constraints: sub_type %s does not belong to type %s",
                ErrorType.VALIDATION,
            )
    for equipment_id in contraints_obj.equipment_ids or []:
        equipment = session.get(Equipment, equipment_id)
        if equipment is None:
            return (
                "Invalid constraints: Equipment with id %s not found" % equipment_id,
                ErrorType.VALIDATION,
            )

    return contraints_obj


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


@log_timing
def update_goal_state(*, session: Session, user_id: UUID, goal: Goal) -> Goal:
    if goal.type == GoalType.MANUAL:
        # Manual goals are updated manually, so we don't update them here
        return goal
    elif goal.type == GoalType.LOCATION:
        # TODO: Location not implemented yet
        return goal
    else:
        contraints = GoalContraints.model_validate(goal.constraints)

        last_updated = goal.current_updated
        stmt = select(Activity).where(Activity.user_id == user_id)

        if contraints.type_id:
            stmt = stmt.where(Activity.type_id == contraints.type_id)
        if contraints.sub_type_id:
            stmt = stmt.where(Activity.sub_type_id == contraints.sub_type_id)

        if goal.month is not None:
            stmt = stmt.where(
                func.extract("year", col(Activity.start)) == goal.year
            ).where(func.extract("month", col(Activity.start)) == goal.month)
        elif goal.week is not None:
            start_date, end_date = get_week_date_range(goal.year, goal.week)
            stmt = stmt.where(col(Activity.start) >= start_date).where(
                col(Activity.start) < end_date
            )
        else:
            stmt = stmt.where(func.extract("year", col(Activity.start)) == goal.year)

        if contraints.equipment_ids:
            stmt = (
                stmt.join(
                    ActivityEquipment,
                    col(Activity.id) == col(ActivityEquipment.activity_id),
                )
                .where(
                    col(ActivityEquipment.equipment_id).in_(contraints.equipment_ids)
                )
                .group_by(col(Activity.id))
                .having(
                    func.count(col(ActivityEquipment.equipment_id))
                    == len(contraints.equipment_ids)
                )
            )

        last_updated_added = False
        if (
            last_updated is not None
            and goal.aggregation != GoalAggregation.AVG_DISTANCE
        ):
            last_updated_added = True
            stmt = stmt.where(col(Activity.created_at) > last_updated)
        activities = session.exec(stmt).all()
        if len(activities) == 0:
            logger.debug("Goal %s: No new activities found", goal.id)
            return goal
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
        goal.current_updated = datetime.now()
        session.add(goal)
        session.commit()
        session.refresh(goal)
        logger.debug("Goal %s: Progrss updated", goal.id)
        return goal
