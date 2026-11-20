from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_501_NOT_IMPLEMENTED,
)

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
)

router = APIRouter(prefix="/strength_training", tags=[Tag.STRENGTH_TRAINING])

logger = structlog.getLogger(__name__)


# -------------------- Exercises --------------------
# Exercisier are defined by the database and the static version data
# So we do not need write routes
# Since the are global no really need to check anyhting about the user
#
@router.get(
    "/exercises/{exercise_id}",
    # response_model=...,
)
def get_exercise(
    user_session: UserSession,
    exercise_id: UUID,
) -> Any:
    _, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/exercises",
    # response_model=...,
)
def get_exercises(
    user_session: UserSession,
) -> Any:
    """Get a list of all exercises"""
    _, session = user_session

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


# TODO: Here we prbably want to also add routes that directly add exercises to a activity?


# -------------------- Exercise Plan --------------------
# user specific
@router.get(
    "/exercise_plans/activity/{activity_id}",
    # response_model=...,
)
def get_plans(
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    """Retrieve a plan"""
    user_id, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/exercise_plans/{plan_id}/activities",
    # response_model=...,
)
def get_plan(
    user_session: UserSession, plan_id: UUID, matches_template: bool = False
) -> Any:
    """Retrieve all activities for assigned to a plan"""
    user_id, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/exercise_plans/{plan_id}",
    # response_model=...,
)
def get_plan(
    user_session: UserSession,
    plan_id: UUID,
) -> Any:
    """Retrieve a plan"""
    user_id, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.patch(
    "/exercise_plans/{plan_id}",
    # response_model=...,
)
def update_plan(
    user_session: UserSession,
    plan_id: UUID,
    data,  # TODO: define update model
) -> Any:
    """Update a plan"""
    user_id, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.delete(
    "/exercise_plans/{plan_id}",
    # response_model=...,
)
def delete_plan(
    user_session: UserSession,
    plan_id: UUID,
) -> Any:
    """Delete a plan"""
    user_id, session = user_session

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/exercise_plans/{plan_id}",
    # response_model=...,
)
def duplicate_plan(
    user_session: UserSession,
    plan_id: UUID,
    name: str,
) -> Any:
    """Duplicates the plan under a new name"""
    user_id, session = user_session

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/exercise_plans",
    # response_model=...,
)
def get_plan(
    user_session: UserSession,
) -> Any:
    """Retrieve all plans"""
    user_id, session = user_session
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/exercise_plans",
    # response_model=...,
)
def create_plan(
    user_session: UserSession,
    data,  # TODO: define update model
) -> Any:
    """Create a plan"""
    user_id, session = user_session

    # TODO: return 409 if plan with same name already exists
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


# -------------------- Exercise Plan + Activity --------------------


@router.post(
    "/activity_exercise_plans/{activity_id}",
    # response_model=...,
)
def add_plan_to_activity(
    user_session: UserSession,
    activity_id: UUID,
    plan_id: UUID,
) -> Any:
    """Link a plan to an activity. This creates the activity specific ActivityExercisePlan"""
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    # TODO: Check plan and return 409 if exists

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/activity_exercise_plans/{activity_id}/exercises",
    # response_model=...,
)
def add_exercise_to_activity_plan(
    user_session: UserSession,
    activity_id: UUID,
    data,
) -> Any:
    """Add a exercise to a activiy. If no plan is assigned, a new ActivityExercisePlan is created"""
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/activity_exercise_plans/{activity_id}/save_as_template",
    # response_model=...,
)
def save_template(
    user_session: UserSession,
    activity_id: UUID,
    data,  # TODO:
) -> Any:
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/activity_exercise_plans/{activity_id}/update_template",
    # response_model=...,
)
def update_template(
    user_session: UserSession,
    activity_id: UUID,
    data,  # TODO:
) -> Any:
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/activity_exercise_plans/{activity_id}",
)
def get_activity_exercise_plans(
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    # TODO: Check if activity has a plan already -> 404

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


# TODO: Do we want additonal routes that delete certain exercises form a
# activity_exercise_plan in addtion to the patch below?


@router.patch(
    "/activity_exercise_plans/{activity_id}",
)
def update_activity_exercise_plan(
    user_session: UserSession,
    activity_id: UUID,
    data,  # TODO: Data model?
) -> Any:
    user_id, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    # TODO: Check if activity has a plan already -> 404

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)
