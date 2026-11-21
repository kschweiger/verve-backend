import json
from importlib.resources import files

import pytest
from sqlmodel import Session, select

from verve_backend.models import (
    Exercise,
    ExerciseCatalogSyncState,
    ExerciseMuscle,
    Muscle,
    MuscleGroup,
    MuscleGroupMember,
)


@pytest.fixture(scope="module")
def bundled_catalog() -> dict:
    return json.loads(
        files("verve_backend").joinpath("data", "exercise_catalog.json").read_text()
    )


def test_seeded_catalog_matches_bundle(db: Session, bundled_catalog: dict) -> None:
    exercises = {row.id: row for row in db.exec(select(Exercise)).all()}
    muscles = {row.id: row.code for row in db.exec(select(Muscle)).all()}
    groups = {row.id: row.code for row in db.exec(select(MuscleGroup)).all()}

    assert {row.code: row.is_active for row in exercises.values()} == {
        item["code"]: item.get("is_active", True)
        for item in bundled_catalog["exercises"]
    }
    assert set(muscles.values()) == set(bundled_catalog["muscles"])
    assert set(groups.values()) == {
        item["code"] for item in bundled_catalog["muscle_groups"]
    }
    assert {
        (exercises[link.exercise_id].code, muscles[link.muscle_id], link.role.value)
        for link in db.exec(select(ExerciseMuscle)).all()
    } == {
        (item["code"], muscle, role)
        for item in bundled_catalog["exercises"]
        for role, field in (
            ("primary", "primary_muscles"),
            ("secondary", "secondary_muscles"),
        )
        for muscle in item[field]
    }
    assert {
        (groups[link.group_id], muscles[link.muscle_id])
        for link in db.exec(select(MuscleGroupMember)).all()
    } == {
        (item["code"], muscle)
        for item in bundled_catalog["muscle_groups"]
        for muscle in item["muscles"]
    }


def test_seed_has_completed_checkpoint(db: Session, bundled_catalog: dict) -> None:
    from verve_backend.cli.import_exercises import SYNC_VERSION, run_import
    from verve_backend.core.exercise_catalog_data import load_catalog

    state = db.get(ExerciseCatalogSyncState, bundled_catalog["source"])
    assert state is not None
    assert state.content_hash == load_catalog().content_hash
    assert state.sync_version == SYNC_VERSION
    assert run_import()["status"] == "unchanged"
