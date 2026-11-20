from uuid import uuid4

import pytest
from pydantic import ValidationError

from verve_backend.models import ExercisePlanCreate, ExercisePlanEntryCreate


def test_plan_create_accepts_repeated_exercises_and_optional_values() -> None:
    exercise_id = uuid4()
    plan = ExercisePlanCreate(
        name="Training",
        entries=[
            ExercisePlanEntryCreate(exercise_id=exercise_id),
            ExercisePlanEntryCreate(exercise_id=exercise_id, weight=10, sets=3),
        ],
    )
    assert len(plan.entries) == 2
    assert plan.entries[0].weight is None
    assert plan.entries[1].sets == 3


@pytest.mark.parametrize("weight", [-1, float("nan"), float("inf")])
def test_entry_rejects_invalid_weight(weight: float) -> None:
    with pytest.raises(ValidationError):
        ExercisePlanEntryCreate(exercise_id=uuid4(), weight=weight)


def test_nested_public_models_and_independent_defaults() -> None:
    from verve_backend.models import ActivityExercisePlanCreate, ExercisePlanPublic

    first = ExercisePlanCreate(name="First")
    second = ExercisePlanCreate(name="Second")
    first.entries.append(ExercisePlanEntryCreate(exercise_id=uuid4()))
    assert second.entries == []
    public = ExercisePlanPublic.model_validate(
        {
            "id": uuid4(),
            "name": "Public",
            "entries": [{"id": 1, "exercise_id": uuid4()}],
        }
    )
    assert public.entries[0].id == 1
    assert ActivityExercisePlanCreate(activity_id=uuid4()).entries == []


@pytest.mark.parametrize(
    ("field", "value"), [("sets", 0), ("repetitions", -1), ("sets", 1.5)]
)
def test_entry_rejects_invalid_counts(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        ExercisePlanEntryCreate.model_validate({"exercise_id": uuid4(), field: value})


def test_empty_plan_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExercisePlanCreate(name="  ")


@pytest.fixture
def model_session(db):  # noqa: ANN201
    from sqlmodel import Session

    from verve_backend.core.db import get_engine

    with Session(get_engine(rls=False)) as session:
        yield session
        session.rollback()


def _sample_data(db):
    from sqlmodel import select

    from verve_backend.models import Activity, Exercise

    activity = db.exec(select(Activity)).first()
    exercise = db.exec(select(Exercise)).first()
    assert activity is not None
    assert exercise is not None
    return activity, exercise


@pytest.mark.parametrize("load_relationships", [False, True])
def test_deleting_template_detaches_activity_and_preserves_entries(
    model_session, load_relationships: bool
) -> None:
    db = model_session
    from verve_backend.models import (
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
        ExercisePlan,
        ExercisePlanEntry,
    )

    activity, exercise = _sample_data(db)
    plan = ExercisePlan(user_id=activity.user_id, name=f"test-{uuid4()}")
    db.add(plan)
    db.flush()
    db.add_all(
        [
            ExercisePlanEntry(
                user_id=activity.user_id,
                plan_id=plan.id,
                exercise_id=exercise.id,
                weight=10,
            ),
            ExercisePlanEntry(
                user_id=activity.user_id,
                plan_id=plan.id,
                exercise_id=exercise.id,
                weight=20,
            ),
        ]
    )
    activity_plan = ActivityExercisePlan(
        user_id=activity.user_id, activity_id=activity.id, source_plan_id=plan.id
    )
    db.add(activity_plan)
    db.flush()
    db.add(
        ActivityExercisePlanEntry(
            user_id=activity.user_id,
            activity_plan_id=activity_plan.id,
            exercise_id=exercise.id,
            weight=30,
        )
    )
    db.flush()
    plan_id, activity_plan_id = plan.id, activity_plan.id
    db.expire_all()
    plan = db.get(ExercisePlan, plan_id)
    if load_relationships:
        assert len(plan.entries) == 2
        assert len(plan.activity_plans) == 1
    db.delete(plan)
    db.flush()
    db.expire_all()
    retained = db.get(ActivityExercisePlan, activity_plan_id)
    assert retained.source_plan_id is None
    assert retained.user_id == activity.user_id
    assert retained.entries[0].weight == 30
    db.rollback()


def test_cross_owner_source_assignment_is_rejected(model_session) -> None:
    db = model_session
    from psycopg.errors import ForeignKeyViolation
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import select

    from verve_backend.models import Activity, ActivityExercisePlan, ExercisePlan

    activity, _ = _sample_data(db)
    other = db.exec(
        select(Activity).where(Activity.user_id != activity.user_id)
    ).first()
    assert other is not None
    plan = ExercisePlan(user_id=other.user_id, name=f"test-{uuid4()}")
    db.add(plan)
    db.flush()
    with pytest.raises(IntegrityError) as error, db.begin_nested():  # noqa: PT012
        db.add(
            ActivityExercisePlan(
                user_id=activity.user_id, activity_id=activity.id, source_plan=plan
            )
        )
        db.flush()
    assert isinstance(error.value.orig, ForeignKeyViolation)
    db.rollback()


def test_deleting_activity_cascades_only_its_plan(model_session) -> None:
    db = model_session
    from verve_backend.models import (
        Activity,
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
        ExercisePlan,
    )

    original, exercise = _sample_data(db)
    values = original.model_dump(exclude={"id", "created_at"})
    activity = Activity(**values)
    template = ExercisePlan(user_id=original.user_id, name=f"test-{uuid4()}")
    db.add_all([activity, template])
    db.flush()
    activity_plan = ActivityExercisePlan(
        user_id=original.user_id, activity_id=activity.id, source_plan_id=template.id
    )
    db.add(activity_plan)
    db.flush()
    entry = ActivityExercisePlanEntry(
        user_id=original.user_id,
        activity_plan_id=activity_plan.id,
        exercise_id=exercise.id,
    )
    db.add(entry)
    db.flush()
    entry_id, plan_id, template_id = entry.id, activity_plan.id, template.id
    assert activity.exercise_plan is not None
    assert activity.exercise_plan.id == plan_id
    db.delete(activity)
    db.flush()
    db.expire_all()
    assert db.get(ActivityExercisePlan, plan_id) is None
    assert db.get(ActivityExercisePlanEntry, entry_id) is None
    assert db.get(ExercisePlan, template_id) is not None
    db.rollback()


def test_rls_isolates_all_plan_tables(model_session) -> None:
    db = model_session
    from psycopg.errors import InsufficientPrivilege
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError
    from sqlmodel import select

    from verve_backend.api.deps import _create_rls_session
    from verve_backend.models import (
        Activity,
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
        ExercisePlan,
        ExercisePlanEntry,
    )

    first, exercise = _sample_data(db)
    second = db.exec(select(Activity).where(Activity.user_id != first.user_id)).first()
    assert second is not None
    owner, other, activity_id, exercise_id = (
        first.user_id,
        second.user_id,
        first.id,
        exercise.id,
    )
    template = ExercisePlan(user_id=owner, name=f"test-{uuid4()}")
    db.add(template)
    db.flush()
    activity_plan = ActivityExercisePlan(
        user_id=owner, activity_id=activity_id, source_plan_id=template.id
    )
    db.add(activity_plan)
    db.flush()
    entry = ExercisePlanEntry(
        user_id=owner, plan_id=template.id, exercise_id=exercise_id
    )
    activity_entry = ActivityExercisePlanEntry(
        user_id=owner, activity_plan_id=activity_plan.id, exercise_id=exercise_id
    )
    db.add_all([entry, activity_entry])
    db.commit()
    template_id, activity_plan_id = template.id, activity_plan.id
    plan_models = (
        ExercisePlan,
        ExercisePlanEntry,
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
    )
    role_is_not_owner = text(
        "SELECT current_user <> (SELECT tableowner FROM pg_tables "
        "WHERE schemaname = current_schema() AND tablename = 'exercise_plans')"
    )
    try:
        with _create_rls_session(owner) as restricted:
            assert restricted.connection().execute(role_is_not_owner).scalar_one()
            for table in plan_models:
                assert (
                    restricted.exec(select(table).where(table.user_id == owner)).first()
                    is not None
                )
        with _create_rls_session(other) as restricted:
            for table in plan_models:
                assert (
                    restricted.exec(select(table).where(table.user_id == owner)).first()
                    is None
                )
            restricted.add(ExercisePlan(user_id=other, name=f"allowed-{uuid4()}"))
            restricted.flush()
            restricted.add(ExercisePlan(user_id=owner, name=f"forbidden-{uuid4()}"))
            with pytest.raises(ProgrammingError) as error:
                restricted.flush()
            assert isinstance(error.value.orig, InsufficientPrivilege)
    finally:
        db.rollback()
        stored = db.get(ActivityExercisePlan, activity_plan_id)
        db.delete(stored)
        stored_template = db.get(ExercisePlan, template_id)
        db.delete(stored_template)
        db.commit()


def test_activity_entries_are_independent_of_template_entries(model_session) -> None:
    db = model_session
    from verve_backend.models import (
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
        ExercisePlan,
        ExercisePlanEntry,
    )

    activity, exercise = _sample_data(db)
    template = ExercisePlan(user_id=activity.user_id, name=f"test-{uuid4()}")
    db.add(template)
    db.flush()
    template_entry = ExercisePlanEntry(
        user_id=activity.user_id,
        plan_id=template.id,
        exercise_id=exercise.id,
        weight=10,
    )
    plan = ActivityExercisePlan(
        user_id=activity.user_id, activity_id=activity.id, source_plan_id=template.id
    )
    db.add_all([template_entry, plan])
    db.flush()
    entry = ActivityExercisePlanEntry(
        user_id=activity.user_id,
        activity_plan_id=plan.id,
        exercise_id=exercise.id,
        weight=10,
    )
    db.add(entry)
    db.flush()
    entry.weight = 20
    db.flush()
    db.expire_all()
    assert db.get(ExercisePlanEntry, template_entry.id).weight == 10
    assert db.get(ActivityExercisePlanEntry, entry.id).weight == 20
    db.rollback()
