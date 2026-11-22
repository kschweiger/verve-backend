from collections import Counter
from collections.abc import Callable, Sequence
from typing import Annotated, Any, TypedDict, cast
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Path, Query
from psycopg.errors import UniqueViolation
from pydantic import Field
from sqlalchemy import delete, distinct, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session, col, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)

from verve_backend.api.common.locale import CatalogLocale, load_translations
from verve_backend.api.common.responses import HTTPErrorResponse
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
    ActivityExercisePlan,
    ActivityExercisePlanEntry,
    ActivityExercisePlanEntryCreate,
    ActivityExercisePlanPublic,
    ActivityPublic,
    Exercise,
    ExerciseMuscle,
    ExerciseMusclePublic,
    ExerciseMuscleRole,
    ExercisePlan,
    ExercisePlanBase,
    ExercisePlanCreate,
    ExercisePlanEntry,
    ExercisePlanEntryBase,
    ExercisePlanEntryCreate,
    ExercisePlanName,
    ExercisePlanPublic,
    ExercisePublic,
    ListResponse,
    Muscle,
    MuscleGroup,
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


def _catalog_labeler(
    session: Session, user_id: str, locale: SupportedLocale | None
) -> Callable[[str, str], str]:
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

    return label


def _load_exercises(
    session: Session,
    user_id: str,
    locale: SupportedLocale | None,
    *,
    exercise_id: UUID | None = None,
) -> list[ExercisePublic]:
    label = _catalog_labeler(session, user_id, locale)
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
    entries: Sequence[ExercisePlanEntryBase],
    existing: Sequence[ExercisePlanEntryBase] = (),
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
    session: Session, plan: ExercisePlan, entries: Sequence[ExercisePlanEntryBase]
) -> None:
    for entry in entries:
        session.add(
            ExercisePlanEntry(
                plan_id=plan.id,
                user_id=plan.user_id,
                exercise_id=entry.exercise_id,
                weight=entry.weight,
                sets=entry.sets,
                repetitions=entry.repetitions,
            )
        )


def _replace_plan_entries(
    session: Session, plan: ExercisePlan, entries: Sequence[ExercisePlanEntryBase]
) -> None:
    session.exec(
        delete(ExercisePlanEntry).where(col(ExercisePlanEntry.plan_id) == plan.id)
    )
    _add_entries(session, plan, entries)


@router.get(
    "/exercise_plans/{plan_id}/activities",
    response_model=ListResponse[ActivityPublic],
    responses={
        404: {"model": HTTPErrorResponse, "description": "Exercise plan not found"}
    },
    summary="List activities linked to an exercise plan",
)
def get_plan_activities(user_session: UserSession, plan_id: UUID) -> Any:
    _, session = user_session
    rows = session.exec(
        select(col(ExercisePlan.id), Activity)
        .select_from(ExercisePlan)
        .outerjoin(
            ActivityExercisePlan,
            col(ActivityExercisePlan.source_plan_id) == col(ExercisePlan.id),
        )
        .outerjoin(
            Activity,
            col(Activity.id) == col(ActivityExercisePlan.activity_id),
        )
        .where(ExercisePlan.id == plan_id)
        .options(selectinload(cast(Any, Activity.tags)))
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Exercise plan not found")
    return ListResponse[ActivityPublic](
        data=[
            ActivityPublic.model_validate(activity)
            for _, activity in rows
            if activity is not None
        ]
    )


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
    description=(
        "Update the name or replace the entry list. "
        'Send `{"entries": []}` to clear the entries.'
    ),
)
def update_plan(
    user_session: UserSession, plan_id: UUID, data: ExercisePlanUpdate
) -> Any:
    _, session = user_session
    plan = _lock_plan(session, plan_id)
    if "entries" in data:
        _validate_entries(session, data["entries"], plan.entries)
        _replace_plan_entries(session, plan, data["entries"])
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
    entries = source.entries
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


class ActivityExercisePlanUpdate(TypedDict):
    entries: list[ActivityExercisePlanEntryCreate]


def _require_activity(
    session: Session, activity_id: UUID, *, lock: bool = False
) -> None:
    statement = select(col(Activity.id)).where(Activity.id == activity_id)
    if lock:
        statement = statement.with_for_update()
    if session.exec(statement).first() is None:
        raise HTTPException(status_code=404, detail="Activity not found")


def _lock_activity_plan(
    session: Session, activity_id: UUID
) -> ActivityExercisePlan | None:
    return session.exec(
        select(ActivityExercisePlan)
        .where(ActivityExercisePlan.activity_id == activity_id)
        .with_for_update()
    ).first()


def _activity_plan_for_template(
    session: Session, activity_id: UUID
) -> ActivityExercisePlan:
    # Activity writers share this lock. Template deletion locks the template
    # before clearing the source reference on the activity plan.
    _require_activity(session, activity_id, lock=True)
    plan = session.exec(
        select(ActivityExercisePlan).where(
            ActivityExercisePlan.activity_id == activity_id
        )
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")
    return plan


def _add_activity_entries(
    session: Session,
    plan: ActivityExercisePlan,
    entries: Sequence[ExercisePlanEntryBase],
) -> None:
    for entry in entries:
        session.add(
            ActivityExercisePlanEntry(
                activity_plan_id=plan.id,
                user_id=plan.user_id,
                exercise_id=entry.exercise_id,
                weight=entry.weight,
                sets=entry.sets,
                repetitions=entry.repetitions,
            )
        )


def _save_activity_plan(
    session: Session, plan: ActivityExercisePlan
) -> ActivityExercisePlanPublic:
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
    _require_activity(session, activity_id, lock=True)
    source = _lock_plan(session, plan_id)
    entries = source.entries
    plan = ActivityExercisePlan(
        user_id=UUID(user_id), activity_id=activity_id, source_plan_id=source.id
    )
    session.add(plan)
    _add_activity_entries(session, plan, entries)
    return _save_activity_plan(session, plan)


@router.post(
    "/activity_exercise_plans/{activity_id}/exercises",
    response_model=ActivityExercisePlanPublic,
    status_code=201,
    responses={
        404: {
            "model": HTTPErrorResponse,
            "description": "Activity or exercise not found",
        },
    },
    summary="Add an exercise to an activity plan",
    description="Append an entry and create an activity plan if needed.",
)
def add_exercise_to_activity_plan(
    user_session: UserSession,
    activity_id: UUID,
    data: ActivityExercisePlanEntryCreate,
) -> Any:
    user_id, session = user_session
    _require_activity(session, activity_id, lock=True)
    _validate_entries(session, [data])
    plan = _lock_activity_plan(session, activity_id)
    if plan is None:
        plan = ActivityExercisePlan(user_id=UUID(user_id), activity_id=activity_id)
        session.add(plan)
    _add_activity_entries(session, plan, [data])
    return _save_activity_plan(session, plan)


@router.delete(
    "/activity_exercise_plans/{activity_id}/entry",
    status_code=HTTP_204_NO_CONTENT,
    responses={
        404: {
            "model": HTTPErrorResponse,
            "description": "Activity, plan or entry not found",
        }
    },
    summary="Remove an entry from an activity plan",
)
def remove_entry_from_activity_plan(
    user_session: UserSession,
    activity_id: UUID,
    entry_id: int,
) -> None:
    _, session = user_session
    _require_activity(session, activity_id, lock=True)
    plan = _lock_activity_plan(session, activity_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")
    entry = session.exec(
        select(ActivityExercisePlanEntry).where(
            ActivityExercisePlanEntry.activity_plan_id == plan.id,
            ActivityExercisePlanEntry.id == entry_id,
        )
    ).first()
    if entry is None:
        raise HTTPException(
            status_code=404, detail="Entry not found in activity exercise plan"
        )
    session.delete(entry)
    session.commit()


@router.post(
    "/activity_exercise_plans/{activity_id}/save_as_template",
    response_model=ExercisePlanPublic,
    status_code=201,
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity or plan not found"},
        409: {"model": HTTPErrorResponse, "description": "Plan name already exists"},
    },
    summary="Save an activity as a new exercise plan template",
    description="Copy entries and link the activity to the new template.",
)
def save_template(
    user_session: UserSession,
    activity_id: UUID,
    data: ExercisePlanBase,
) -> Any:
    _, session = user_session
    activity_plan = _activity_plan_for_template(session, activity_id)
    entries = activity_plan.entries
    template = ExercisePlan(name=data.name, user_id=activity_plan.user_id)
    session.add(template)
    _add_entries(session, template, entries)
    activity_plan.source_plan = template
    return _save_plan(session, template)


@router.post(
    "/activity_exercise_plans/{activity_id}/update_template",
    response_model=ExercisePlanPublic,
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity or plan not found"},
        409: {
            "model": HTTPErrorResponse,
            "description": "Activity has no linked template",
        },
    },
    summary="Update the linked exercise plan template",
    description="Replace template entries with copies of this activity's entries.",
)
def update_template(
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    activity_plan = _activity_plan_for_template(session, activity_id)
    source_plan_id = activity_plan.source_plan_id
    template = (
        session.get(ExercisePlan, source_plan_id, with_for_update=True)
        if source_plan_id is not None
        else None
    )
    if template is None:
        raise HTTPException(status_code=409, detail="Activity has no linked template")
    _replace_plan_entries(session, template, activity_plan.entries)
    return _save_plan(session, template)


@router.get(
    "/activity_exercise_plans/{activity_id}",
    response_model=ActivityExercisePlanPublic,
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity or plan not found"}
    },
    summary="Get an activity exercise plan",
    description="Retrieve the exercise plan snapshot for an activity.",
)
def get_activity_exercise_plans(
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    _require_activity(session, activity_id)
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


@router.delete(
    "/activity_exercise_plans/{activity_id}",
    status_code=HTTP_204_NO_CONTENT,
    responses={
        404: {
            "model": HTTPErrorResponse,
            "description": "Activity or activity exercise plan not found",
        }
    },
    summary="Remove an activity exercise plan",
)
def delete_activity_exercise_plan(
    user_session: UserSession,
    activity_id: UUID,
) -> None:
    _, session = user_session
    _require_activity(session, activity_id, lock=True)
    plan = _lock_activity_plan(session, activity_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")
    session.delete(plan)
    session.commit()


class ActivityMuscleGroupPublic(MuscleGroupPublic):
    role: ExerciseMuscleRole = Field(
        description="Primary if any contributing muscle is primary; "
        "otherwise secondary."
    )
    exercise_count: int = Field(description="Number of distinct catalog exercises.")
    exercise_ids: list[UUID] = Field(
        description="Distinct contributing catalog exercise IDs."
    )


@router.get(
    "/activity_exercise_plans/{activity_id}/muscle_groups",
    response_model=ListResponse[ActivityMuscleGroupPublic],
    responses={
        404: {"model": HTTPErrorResponse, "description": "Activity or plan not found"}
    },
    summary="Get muscle groups for an activity exercise plan",
)
def get_activity_muscle_groups(
    user_session: UserSession,
    activity_id: UUID,
    locale: CatalogLocale = None,
) -> Any:
    user_id, session = user_session
    _require_activity(session, activity_id)
    plan_id = session.exec(
        select(ActivityExercisePlan.id).where(
            ActivityExercisePlan.activity_id == activity_id
        )
    ).first()
    if plan_id is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")

    rows = session.exec(
        select(
            MuscleGroup,
            func.bool_or(col(ExerciseMuscle.role) == ExerciseMuscleRole.PRIMARY),
            func.array_agg(distinct(col(ActivityExercisePlanEntry.exercise_id))),
        )
        .join(MuscleGroupMember, col(MuscleGroupMember.group_id) == col(MuscleGroup.id))
        .join(
            ExerciseMuscle,
            col(ExerciseMuscle.muscle_id) == col(MuscleGroupMember.muscle_id),
        )
        .join(
            ActivityExercisePlanEntry,
            col(ActivityExercisePlanEntry.exercise_id)
            == col(ExerciseMuscle.exercise_id),
        )
        .where(ActivityExercisePlanEntry.activity_plan_id == plan_id)
        .group_by(col(MuscleGroup.id))
    ).all()
    label = _catalog_labeler(session, user_id, locale)
    return ListResponse[ActivityMuscleGroupPublic](
        data=[
            ActivityMuscleGroupPublic(
                id=group.id,
                code=group.code,
                name=label("muscle_groups", group.code),
                role=ExerciseMuscleRole.PRIMARY
                if is_primary
                else ExerciseMuscleRole.SECONDARY,
                exercise_count=len(exercise_ids),
                exercise_ids=exercise_ids,
            )
            for group, is_primary, exercise_ids in rows
        ]
    )


@router.patch(
    "/activity_exercise_plans/{activity_id}",
    response_model=ActivityExercisePlanPublic,
    responses={
        404: {
            "model": HTTPErrorResponse,
            "description": "Activity, plan or exercise not found",
        }
    },
    summary="Replace entries in an activity plan",
    description='Replace all entries. Send `{"entries": []}` to clear the plan.',
)
def update_activity_exercise_plan(
    user_session: UserSession,
    activity_id: UUID,
    data: ActivityExercisePlanUpdate,
) -> Any:
    _, session = user_session
    _require_activity(session, activity_id, lock=True)
    plan = _lock_activity_plan(session, activity_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Activity exercise plan not found")
    entries = data["entries"]
    _validate_entries(session, entries, plan.entries)
    session.exec(
        delete(ActivityExercisePlanEntry).where(
            col(ActivityExercisePlanEntry.activity_plan_id) == plan.id
        )
    )
    _add_activity_entries(session, plan, entries)
    return _save_activity_plan(session, plan)
