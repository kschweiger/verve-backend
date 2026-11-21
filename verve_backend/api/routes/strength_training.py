from collections import Counter
from collections.abc import Sequence
from typing import Annotated, Any, TypedDict, cast
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Path, Query
from psycopg.errors import UniqueViolation
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, col, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
    HTTP_501_NOT_IMPLEMENTED,
)

from verve_backend.api.common.locale import CatalogLocale, load_translations
from verve_backend.api.common.responses import HTTPErrorResponse
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
    ActivityExercisePlan,
    ActivityExercisePlanEntry,
    ActivityExercisePlanPublic,
    Exercise,
    ExerciseMuscle,
    ExerciseMusclePublic,
    ExercisePlan,
    ExercisePlanCreate,
    ExercisePlanEntry,
    ExercisePlanEntryCreate,
    ExercisePlanName,
    ExercisePlanPublic,
    ExercisePublic,
    ListResponse,
    Muscle,
    MuscleGroupMember,
    MuscleGroupPublic,
    SupportedLocale,
    UserSettings,
)

router = APIRouter(prefix="/strength_training", tags=[Tag.STRENGTH_TRAINING])

logger = structlog.getLogger(__name__)


# -------------------- Exercises --------------------
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": HTTPErrorResponse, "description": "Inactive user"},
    401: {"model": HTTPErrorResponse, "description": "Authentication required"},
    403: {"model": HTTPErrorResponse, "description": "Invalid credentials"},
    404: {"model": HTTPErrorResponse, "description": "Exercise or user not found"},
}


def _query_exercises(
    session: Session, *, exercise_id: UUID | None = None
) -> Sequence[Exercise]:
    statement = select(Exercise).options(
        selectinload(cast(Any, Exercise.muscle_links))
        .selectinload(cast(Any, ExerciseMuscle.muscle))
        .selectinload(cast(Any, Muscle.group_links))
        .selectinload(cast(Any, MuscleGroupMember.group))
    )
    if exercise_id is None:
        statement = statement.where(col(Exercise.is_active).is_(True))
    else:
        statement = statement.where(Exercise.id == exercise_id)
    return session.exec(statement.order_by(Exercise.code)).all()


def _load_exercises(
    session: Session,
    user_id: str,
    locale: SupportedLocale | None,
    *,
    exercise_id: UUID | None = None,
) -> list[ExercisePublic]:
    settings = session.get(UserSettings, UUID(user_id)) if locale is None else None
    locale = locale or (settings.locale if settings else SupportedLocale.EN)
    translations = load_translations(locale)
    english = load_translations(SupportedLocale.EN)

    def label(kind: str, code: str) -> str:
        return (
            translations.get(kind, {}).get(code)
            or english.get(kind, {}).get(code)
            or code
        )

    exercises = _query_exercises(session, exercise_id=exercise_id)
    return [
        ExercisePublic(
            id=exercise.id,
            code=exercise.code,
            name=label("exercises", exercise.code),
            is_active=exercise.is_active,
            muscles=[
                ExerciseMusclePublic(
                    id=link.muscle.id,
                    code=link.muscle.code,
                    name=label("muscles", link.muscle.code),
                    role=link.role,
                    muscle_groups=[
                        MuscleGroupPublic(
                            id=member.group.id,
                            code=member.group.code,
                            name=label("muscle_groups", member.group.code),
                        )
                        for member in sorted(
                            link.muscle.group_links, key=lambda m: m.group.code
                        )
                    ],
                )
                for link in sorted(
                    exercise.muscle_links, key=lambda item: item.muscle.code
                )
            ],
        )
        for exercise in exercises
    ]


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExercisePublic,
    responses=_ERROR_RESPONSES,
    summary="Get an exercise by ID",
    description="Look up an exercise, including inactive exercises used in "
    "historical records.",
)
def get_exercise(
    user_session: UserSession,
    exercise_id: UUID = Path(description="UUID of the exercise to retrieve."),
    locale: CatalogLocale = None,
) -> Any:
    user_id, session = user_session
    exercises = _load_exercises(session, user_id, locale, exercise_id=exercise_id)
    if not exercises:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Exercise not found")
    return exercises[0]


@router.get(
    "/exercises",
    response_model=ListResponse[ExercisePublic],
    responses={
        **_ERROR_RESPONSES,
        404: {"model": HTTPErrorResponse, "description": "User not found"},
    },
    summary="List active exercises",
    description="List active exercises available for selection.",
)
def get_exercises(
    user_session: UserSession,
    locale: CatalogLocale = None,
) -> Any:
    user_id, session = user_session
    return ListResponse[ExercisePublic](data=_load_exercises(session, user_id, locale))


# TODO: Consider routes that directly add exercises to an activity.


# -------------------- Exercise Plan --------------------
class ExercisePlanUpdate(TypedDict, total=False):
    name: ExercisePlanName
    entries: list[ExercisePlanEntryCreate]


_PLAN_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": HTTPErrorResponse, "description": "Plan or exercise not found"}
}
_PLAN_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_PLAN_NOT_FOUND,
    409: {"model": HTTPErrorResponse, "description": "Plan name already exists"},
}


def _lock_plan(session: Session, plan_id: UUID) -> ExercisePlan:
    plan = session.exec(
        select(ExercisePlan).where(ExercisePlan.id == plan_id).with_for_update()
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Exercise plan not found")
    return plan


def _validate_entries(
    session: Session,
    entries: list[ExercisePlanEntryCreate],
    existing: Sequence[ExercisePlanEntry] = (),
) -> None:
    requested = Counter(entry.exercise_id for entry in entries)
    if not requested:
        return
    exercises = session.exec(
        select(Exercise).where(col(Exercise.id).in_(requested))
    ).all()
    active = {exercise.id for exercise in exercises if exercise.is_active}
    existing_counts = Counter(entry.exercise_id for entry in existing)
    if any(
        exercise_id not in active and count > existing_counts[exercise_id]
        for exercise_id, count in requested.items()
    ):
        raise HTTPException(status_code=404, detail="Exercise not found or unavailable")


def _save_plan(session: Session, plan: ExercisePlan) -> ExercisePlanPublic:
    try:
        session.flush()
        session.expire(plan, ["entries"])
        result = ExercisePlanPublic.model_validate(plan)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        error = exc.orig
        if (
            isinstance(error, UniqueViolation)
            and error.diag.constraint_name == "uix_exercise_plans_user_name"
        ):
            raise HTTPException(
                status_code=409, detail="Exercise plan name already exists"
            ) from exc
        raise
    return result


def _add_entries(
    session: Session, plan: ExercisePlan, entries: list[ExercisePlanEntryCreate]
) -> None:
    for entry in entries:
        session.add(
            ExercisePlanEntry(
                **entry.model_dump(), plan_id=plan.id, user_id=plan.user_id
            )
        )


@router.get(
    "/exercise_plans/{plan_id}/activities",
    # response_model=...,
)
def get_plan_activities(
    user_session: UserSession, plan_id: UUID, matches_template: bool = False
) -> Any:
    """Retrieve all activities for assigned to a plan"""
    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/exercise_plans/{plan_id}",
    response_model=ExercisePlanPublic,
    responses=_PLAN_NOT_FOUND,
)
def get_plan(
    user_session: UserSession,
    plan_id: UUID,
) -> Any:
    _, session = user_session
    plan = (
        session.exec(
            select(ExercisePlan)
            .where(ExercisePlan.id == plan_id)
            .options(joinedload(cast(Any, ExercisePlan.entries)))
        )
        .unique()
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Exercise plan not found")
    return plan


@router.patch(
    "/exercise_plans/{plan_id}",
    response_model=ExercisePlanPublic,
    responses=_PLAN_WRITE_ERRORS,
)
def update_plan(
    user_session: UserSession, plan_id: UUID, data: ExercisePlanUpdate
) -> Any:
    _, session = user_session
    plan = _lock_plan(session, plan_id)
    if "entries" in data:
        _validate_entries(session, data["entries"], plan.entries)
        session.exec(
            delete(ExercisePlanEntry).where(col(ExercisePlanEntry.plan_id) == plan.id)
        )
        _add_entries(session, plan, data["entries"])
    if "name" in data:
        plan.name = data["name"]
    return _save_plan(session, plan)


@router.delete(
    "/exercise_plans/{plan_id}",
    status_code=HTTP_204_NO_CONTENT,
    responses=_PLAN_NOT_FOUND,
)
def delete_plan(user_session: UserSession, plan_id: UUID) -> None:
    _, session = user_session
    plan = _lock_plan(session, plan_id)
    session.delete(plan)
    session.commit()


@router.post(
    "/exercise_plans/{plan_id}",
    response_model=ExercisePlanPublic,
    status_code=201,
    responses=_PLAN_WRITE_ERRORS,
)
def duplicate_plan(
    user_session: UserSession,
    plan_id: UUID,
    name: Annotated[ExercisePlanName, Query()],
) -> Any:
    user_id, session = user_session
    source = _lock_plan(session, plan_id)
    entries = [
        ExercisePlanEntryCreate.model_validate(entry) for entry in source.entries
    ]
    plan = ExercisePlan(name=name, user_id=UUID(user_id))
    session.add(plan)
    _add_entries(session, plan, entries)
    return _save_plan(session, plan)


@router.get("/exercise_plans", response_model=ListResponse[ExercisePlanPublic])
def list_plans(user_session: UserSession) -> Any:
    _, session = user_session
    plans = (
        session.exec(
            select(ExercisePlan)
            .options(joinedload(cast(Any, ExercisePlan.entries)))
            .order_by(ExercisePlan.name)
        )
        .unique()
        .all()
    )
    return ListResponse[ExercisePlanPublic](
        data=[ExercisePlanPublic.model_validate(plan) for plan in plans]
    )


@router.post(
    "/exercise_plans",
    response_model=ExercisePlanPublic,
    status_code=201,
    responses=_PLAN_WRITE_ERRORS,
)
def create_plan(user_session: UserSession, data: ExercisePlanCreate) -> Any:
    user_id, session = user_session
    _validate_entries(session, data.entries)
    plan = ExercisePlan(name=data.name, user_id=UUID(user_id))
    session.add(plan)
    _add_entries(session, plan, data.entries)
    return _save_plan(session, plan)


# -------------------- Exercise Plan + Activity --------------------


@router.post(
    "/activity_exercise_plans/{activity_id}",
    response_model=ActivityExercisePlanPublic,
    status_code=201,
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity or plan not found"},
        409: {"model": HTTPErrorResponse, "description": "Activity already has a plan"},
    },
    summary="Apply an exercise plan to an activity",
    description="Create an independent snapshot of the template for this activity.",
)
def add_plan_to_activity(
    user_session: UserSession,
    activity_id: UUID,
    plan_id: UUID,
) -> Any:
    user_id, session = user_session
    activity = session.exec(
        select(Activity).where(Activity.id == activity_id).with_for_update()
    ).first()
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    source = _lock_plan(session, plan_id)
    entries = [
        ExercisePlanEntryCreate.model_validate(entry) for entry in source.entries
    ]
    plan = ActivityExercisePlan(
        user_id=UUID(user_id), activity_id=activity.id, source_plan_id=source.id
    )
    session.add(plan)
    for entry in entries:
        session.add(
            ActivityExercisePlanEntry(
                **entry.model_dump(), activity_plan_id=plan.id, user_id=plan.user_id
            )
        )
    try:
        session.flush()
        session.expire(plan, ["entries"])
        result = ActivityExercisePlanPublic.model_validate(plan)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        error = exc.orig
        if (
            isinstance(error, UniqueViolation)
            and error.diag.constraint_name == "uix_activity_exercise_plans_activity"
        ):
            raise HTTPException(
                status_code=409, detail="Activity already has an exercise plan"
            ) from exc
        raise
    return result


@router.post(
    "/activity_exercise_plans/{activity_id}/exercises",
    # response_model=...,
)
def add_exercise_to_activity_plan(
    user_session: UserSession,
    activity_id: UUID,
    data,
) -> Any:
    """Add an exercise to an activity, creating a plan if needed."""
    _, session = user_session

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
    _, session = user_session

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
    _, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/activity_exercise_plans/{activity_id}",
    response_model=ActivityExercisePlanPublic,
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity plan not found"}
    },
    summary="Get an activity exercise plan",
    description="Retrieve the exercise plan snapshot for an activity.",
)
def get_activity_exercise_plans(
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    plan = (
        session.exec(
            select(ActivityExercisePlan)
            .where(ActivityExercisePlan.activity_id == activity_id)
            .options(joinedload(cast(Any, ActivityExercisePlan.entries)))
        )
        .unique()
        .first()
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")
    return plan


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
    _, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    # TODO: Check if activity has a plan already -> 404

    raise HTTPException(status_code=HTTP_501_NOT_IMPLEMENTED)
