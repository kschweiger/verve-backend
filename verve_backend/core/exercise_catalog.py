"""RepDB mapping. Source and license: https://github.com/RepDB/exercise-dataset."""

from dataclasses import dataclass, field

from sqlmodel import Session, select

from verve_backend.models import Exercise, ExerciseMuscle, ExerciseMuscleRole, Muscle


@dataclass(frozen=True)
class SourceExercise:
    id: str
    name_en: str
    name_de: str | None
    muscles: dict[str, ExerciseMuscleRole]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    muscles_created: int = 0
    warnings: list[str] = field(default_factory=list)
    names: dict[str, dict[str, str]] = field(
        default_factory=lambda: {"en": {}, "de": {}}
    )


def required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty string")
    return value


def validate_snapshot(data: object) -> list[SourceExercise]:
    if not isinstance(data, dict) or not isinstance(data.get("exercises"), list):
        raise ValueError("Expected an object with an exercises array")
    result = []
    seen = set()
    for item in data["exercises"]:
        if not isinstance(item, dict):
            raise ValueError("Expected an exercise object")
        identity = required_string(item.get("id"))
        if identity in seen:
            raise ValueError(f"Duplicate exercise: {identity}")
        seen.add(identity)
        english = required_string(item.get("name_en"))
        german = item.get("name_de")
        if german is not None and not isinstance(german, str):
            raise ValueError(f"Invalid German name: {identity}")
        muscles = {}
        for key, role in (
            ("primary_muscles", ExerciseMuscleRole.PRIMARY),
            ("secondary_muscles", ExerciseMuscleRole.SECONDARY),
        ):
            values = item.get(key, [])
            if not isinstance(values, list):
                raise ValueError(f"Invalid muscle list: {identity}")
            for value in values:
                code = required_string(value)
                if code in muscles:
                    raise ValueError(f"Duplicate muscle: {identity}/{code}")
                muscles[code] = role
        result.append(SourceExercise(identity, english, german or None, muscles))
    return result


def import_repdb(
    session: Session,
    snapshot: list[SourceExercise],
    revision: str,
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Reconcile a validated snapshot; the caller owns commit and rollback."""
    required_string(revision)
    result = ImportResult()
    proposed_muscles: set[str] = set()
    for item in snapshot:
        exercise = session.exec(
            select(Exercise).where(
                Exercise.source == "repdb", Exercise.source_id == item.id
            )
        ).first()
        is_new = exercise is None
        if exercise is None:
            if session.exec(select(Exercise).where(Exercise.code == item.id)).first():
                raise ValueError(f"Exercise code collision: {item.id}")
            exercise = Exercise(
                code=item.id,
                source="repdb",
                source_id=item.id,
                source_revision=revision,
            )
            if not dry_run:
                session.add(exercise)
            result.created += 1
            changed = False
        else:
            changed = exercise.source_revision != revision
            if not dry_run:
                exercise.source_revision = revision
        if not dry_run:
            session.flush()
        links = {
            link.muscle.code: link
            for link in session.exec(
                select(ExerciseMuscle).where(ExerciseMuscle.exercise_id == exercise.id)
            ).all()
        }
        changed |= {code: link.role for code, link in links.items()} != item.muscles
        for code, link in links.items():
            if code not in item.muscles and not dry_run:
                session.delete(link)
        for code, role in item.muscles.items():
            if code in links:
                if not dry_run:
                    links[code].role = role
                continue
            muscle = session.exec(select(Muscle).where(Muscle.code == code)).first()
            if muscle is None:
                muscle = Muscle(code=code)
                if not dry_run:
                    session.add(muscle)
                    session.flush()
                if code not in proposed_muscles:
                    result.muscles_created += 1
                    proposed_muscles.add(code)
            if not dry_run:
                session.add(
                    ExerciseMuscle(
                        exercise_id=exercise.id, muscle_id=muscle.id, role=role
                    )
                )
        if not is_new:
            if changed:
                result.updated += 1
            else:
                result.unchanged += 1
        result.names["en"][exercise.code] = item.name_en
        if item.name_de and item.name_de.strip():
            result.names["de"][exercise.code] = item.name_de
        else:
            result.warnings.append(f"Missing German translation: {item.id}")
        if not item.muscles:
            result.warnings.append(f"No muscle assignments: {item.id}")
    if not dry_run:
        session.flush()
    return result
