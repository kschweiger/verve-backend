import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from verve_backend.models import Exercise, ExerciseMuscle, Muscle, MuscleGroup


def test_catalog_relationships(db: Session) -> None:
    """Reload the seeded catalog to check roles and overlapping memberships.
    Empty exercises and groups must also remain valid without associations.
    """
    db.expire_all()
    squat = db.exec(select(Exercise).where(Exercise.code == "squat")).one()
    assert sorted(link.role for link in squat.muscle_links) == [
        "primary",
        "primary",
        "secondary",
        "secondary",
    ]
    quadriceps = db.exec(select(Muscle).where(Muscle.code == "quadriceps")).one()
    assert {link.group.code for link in quadriceps.group_links} == {
        "legs",
        "lower_body",
    }
    assert all(link.exercise.id == squat.id for link in quadriceps.exercise_links)
    unmapped = db.exec(select(Exercise).where(Exercise.code == "unmapped")).one()
    empty = db.exec(select(MuscleGroup).where(MuscleGroup.code == "empty")).one()
    assert unmapped.muscle_links == []
    assert empty.members == []


def test_exercise_deactivation(db: Session) -> None:
    """Deactivation preserves the seeded exercise and its muscle assignments.
    Restore the active flag afterward so the shared baseline remains unchanged.
    """
    exercise = db.exec(select(Exercise).where(Exercise.code == "squat")).one()
    identity, code = exercise.id, exercise.code
    links = {(link.muscle_id, link.role) for link in exercise.muscle_links}
    try:
        exercise.is_active = False
        db.commit()
        db.expire_all()
        assert not exercise.is_active
        assert exercise.id == identity
        assert exercise.code == code
        assert {(link.muscle_id, link.role) for link in exercise.muscle_links} == links
    finally:
        exercise.is_active = True
        db.commit()


@pytest.mark.parametrize("loaded", [False, True])
@pytest.mark.parametrize(
    ("model", "code", "collections"),
    [
        (Exercise, "squat", ["muscle_links"]),
        (Muscle, "quadriceps", ["exercise_links", "group_links"]),
        (MuscleGroup, "legs", ["members"]),
    ],
)
def test_referenced_parent_deletion(
    db: Session, model, code, collections, loaded
) -> None:
    """ORM deletion must preserve references with loaded or unloaded collections.
    A savepoint contains the rejected deletion and leaves seeded links intact.
    """
    parent = db.exec(select(model).where(model.code == code)).one()
    db.expire(parent)
    if loaded:
        for collection in collections:
            assert getattr(parent, collection)
    with pytest.raises(IntegrityError), db.begin_nested():  # noqa: PT012
        db.delete(parent)
        db.flush()
    db.expire_all()
    for collection in collections:
        assert getattr(parent, collection)


@pytest.mark.parametrize("model", [Exercise, Muscle, MuscleGroup])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_catalog_validation_rejects_invalid_codes(model, value) -> None:
    data = dict(code=value, source="test", source_id="squat", source_revision="1")
    with pytest.raises(ValidationError) as error:
        model.model_validate(data)
    assert ("code",) in [item["loc"] for item in error.value.errors()]


@pytest.mark.parametrize("field", ["source", "source_id", "source_revision"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_exercise_validation_rejects_invalid_source_fields(field, value) -> None:
    data = dict(code="squat", source="test", source_id="squat", source_revision="1")
    data[field] = value
    with pytest.raises(ValidationError) as error:
        Exercise.model_validate(data)
    assert (field,) in [item["loc"] for item in error.value.errors()]


def test_exercise_muscle_validation_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError) as error:
        ExerciseMuscle.model_validate(dict(role="tertiary"))
    assert ("role",) in [item["loc"] for item in error.value.errors()]
