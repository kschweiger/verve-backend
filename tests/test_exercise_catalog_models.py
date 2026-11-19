from collections.abc import Generator

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from verve_backend.models import (
    Exercise,
    ExerciseMuscle,
    ExerciseMuscleRole,
    Muscle,
    MuscleGroup,
    MuscleGroupMember,
)


@pytest.fixture
def catalog(db: Session) -> Generator[Session]:
    """Keep synthetic edge cases in a separate transaction that rolls back."""
    with Session(db.get_bind()) as session:
        quadriceps = Muscle(code="model_test_quadriceps")
        glutes = Muscle(code="model_test_glutes")
        calves = Muscle(code="model_test_calves")
        core = Muscle(code="model_test_core")
        squat = Exercise(code="model_test_squat")
        unmapped = Exercise(code="model_test_unmapped")
        legs = MuscleGroup(code="model_test_legs")
        lower_body = MuscleGroup(code="model_test_lower_body")
        empty = MuscleGroup(code="model_test_empty")
        session.add_all(
            [quadriceps, glutes, calves, core, squat, unmapped, legs, lower_body, empty]
        )
        session.flush()
        session.add_all(
            [
                ExerciseMuscle(exercise_id=squat.id, muscle_id=muscle.id, role=role)
                for muscle, role in (
                    (quadriceps, ExerciseMuscleRole.PRIMARY),
                    (glutes, ExerciseMuscleRole.PRIMARY),
                    (calves, ExerciseMuscleRole.SECONDARY),
                    (core, ExerciseMuscleRole.SECONDARY),
                )
            ]
        )
        session.add_all(
            [
                MuscleGroupMember(group_id=group.id, muscle_id=muscle.id)
                for group, muscle in (
                    (legs, quadriceps),
                    (legs, calves),
                    (lower_body, quadriceps),
                    (lower_body, glutes),
                )
            ]
        )
        session.flush()
        yield session


def test_catalog_relationships(catalog: Session) -> None:
    """Reload a local catalog to check roles and overlapping memberships.
    Empty exercises and groups must also remain valid without associations.
    """
    catalog.expire_all()
    squat = catalog.exec(
        select(Exercise).where(Exercise.code == "model_test_squat")
    ).one()
    assert sorted(link.role for link in squat.muscle_links) == [
        "primary",
        "primary",
        "secondary",
        "secondary",
    ]
    assert {link.role.value for link in squat.muscle_links} == {
        ExerciseMuscleRole.PRIMARY.value,
        ExerciseMuscleRole.SECONDARY.value,
    }
    quadriceps = catalog.exec(
        select(Muscle).where(Muscle.code == "model_test_quadriceps")
    ).one()
    assert {link.group.code for link in quadriceps.group_links} == {
        "model_test_legs",
        "model_test_lower_body",
    }
    assert all(link.exercise.id == squat.id for link in quadriceps.exercise_links)
    unmapped = catalog.exec(
        select(Exercise).where(Exercise.code == "model_test_unmapped")
    ).one()
    empty = catalog.exec(
        select(MuscleGroup).where(MuscleGroup.code == "model_test_empty")
    ).one()
    assert unmapped.muscle_links == []
    assert empty.members == []


def test_exercise_deactivation(catalog: Session) -> None:
    """Deactivation preserves the local exercise and its muscle assignments."""
    exercise = catalog.exec(
        select(Exercise).where(Exercise.code == "model_test_squat")
    ).one()
    identity, code = exercise.id, exercise.code
    links = {(link.muscle_id, link.role) for link in exercise.muscle_links}
    exercise.is_active = False
    catalog.flush()
    catalog.expire_all()
    assert not exercise.is_active
    assert exercise.id == identity
    assert exercise.code == code
    assert {(link.muscle_id, link.role) for link in exercise.muscle_links} == links


@pytest.mark.parametrize("loaded", [False, True])
@pytest.mark.parametrize(
    ("model", "code", "collections"),
    [
        (Exercise, "model_test_squat", ["muscle_links"]),
        (Muscle, "model_test_quadriceps", ["exercise_links", "group_links"]),
        (MuscleGroup, "model_test_legs", ["members"]),
    ],
)
def test_referenced_parent_deletion(
    catalog: Session, model, code, collections, loaded
) -> None:
    """ORM deletion must preserve references with loaded or unloaded collections.
    A savepoint contains the rejected deletion and leaves local links intact.
    """
    parent = catalog.exec(select(model).where(model.code == code)).one()
    catalog.expire(parent)
    if loaded:
        for collection in collections:
            assert getattr(parent, collection)
    with pytest.raises(IntegrityError), catalog.begin_nested():  # noqa: PT012
        catalog.delete(parent)
        catalog.flush()
    catalog.expire_all()
    for collection in collections:
        assert getattr(parent, collection)


@pytest.mark.parametrize("model", [Exercise, Muscle, MuscleGroup])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_catalog_validation_rejects_invalid_codes(model, value) -> None:
    data = dict(code=value)
    with pytest.raises(ValidationError) as error:
        model.model_validate(data)
    assert ("code",) in [item["loc"] for item in error.value.errors()]


def test_exercise_muscle_validation_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError) as error:
        ExerciseMuscle.model_validate(dict(role="tertiary"))
    assert ("role",) in [item["loc"] for item in error.value.errors()]
