"""Reconcile the bundled catalog; the caller owns the transaction."""

from dataclasses import dataclass, field

from sqlmodel import Session, select

from verve_backend.core.exercise_catalog_data import CatalogSnapshot
from verve_backend.models import (
    Exercise,
    ExerciseMuscle,
    Muscle,
    MuscleGroup,
    MuscleGroupMember,
)


@dataclass
class CatalogSyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    muscles_created: int = 0
    groups_created: int = 0
    groups_updated: int = 0
    groups_unchanged: int = 0
    groups_deleted: int = 0
    group_memberships_created: int = 0
    group_memberships_removed: int = 0
    warnings: list[str] = field(default_factory=list)


def sync_catalog(
    session: Session, snapshot: CatalogSnapshot, *, dry_run: bool = False
) -> CatalogSyncResult:
    """Keep exercise identities and replace the complete display-group definition."""
    result = CatalogSyncResult()
    with session.no_autoflush:
        muscles = {row.code: row for row in session.exec(select(Muscle)).all()}
        exercises = {row.code: row for row in session.exec(select(Exercise)).all()}
        groups = {row.code: row for row in session.exec(select(MuscleGroup)).all()}
        exercise_links = {}
        for link in session.exec(select(ExerciseMuscle)).all():
            exercise_links.setdefault(link.exercise_id, {})[link.muscle_id] = link
        group_links = {}
        for member in session.exec(select(MuscleGroupMember)).all():
            group_links.setdefault(member.group_id, {})[member.muscle_id] = member

    for code in snapshot.muscles:
        if code not in muscles:
            muscle = Muscle(code=code)
            muscles[code] = muscle
            result.muscles_created += 1
            if not dry_run:
                session.add(muscle)
    if not dry_run:
        session.flush()

    for item in snapshot.exercises:
        exercise = exercises.get(item.code)
        links = exercise_links.get(exercise.id, {}) if exercise else {}
        desired = {muscles[code].id: role for code, role in item.muscles.items()}
        if exercise is None:
            exercise = Exercise(code=item.code, is_active=item.is_active)
            result.created += 1
            if not dry_run:
                session.add(exercise)
                session.flush()
        elif (
            exercise.is_active != item.is_active
            or {key: link.role for key, link in links.items()} != desired
        ):
            result.updated += 1
        else:
            result.unchanged += 1
        if not item.muscles:
            result.warnings.append(f"No muscle assignments: {item.code}")
        if dry_run:
            continue
        exercise.is_active = item.is_active
        for muscle_id, link in links.items():
            if muscle_id not in desired:
                session.delete(link)
        for muscle_id, role in desired.items():
            if muscle_id in links:
                links[muscle_id].role = role
            else:
                session.add(
                    ExerciseMuscle(
                        exercise_id=exercise.id, muscle_id=muscle_id, role=role
                    )
                )

    desired_codes = {item.code for item in snapshot.groups}
    removed_groups = [
        group for code, group in groups.items() if code not in desired_codes
    ]
    result.groups_deleted = len(removed_groups)
    for group in removed_groups:
        links = group_links.get(group.id, {})
        result.group_memberships_removed += len(links)
        if not dry_run:
            for member in links.values():
                session.delete(member)
    # RESTRICT foreign keys require the link deletes to finish before parent deletes.
    if not dry_run:
        session.flush()
        for group in removed_groups:
            session.delete(group)

    for item in snapshot.groups:
        group = groups.get(item.code)
        links = group_links.get(group.id, {}) if group else {}
        desired_members = {muscles[code].id for code in item.muscles}
        if group is None:
            group = MuscleGroup(code=item.code)
            result.groups_created += 1
            if not dry_run:
                session.add(group)
                session.flush()
        elif set(links) != desired_members:
            result.groups_updated += 1
        else:
            result.groups_unchanged += 1
        result.group_memberships_created += len(desired_members - links.keys())
        result.group_memberships_removed += len(links.keys() - desired_members)
        if dry_run:
            continue
        for muscle_id, member in links.items():
            if muscle_id not in desired_members:
                session.delete(member)
        for muscle_id in desired_members - links.keys():
            session.add(MuscleGroupMember(group_id=group.id, muscle_id=muscle_id))
    if not dry_run:
        session.flush()
    return result
