import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlmodel import Session, select

from verve_backend.cli import import_exercises as cli
from verve_backend.core.exercise_catalog import import_repdb, validate_snapshot
from verve_backend.models import (
    Exercise,
    ExerciseCatalogImportState,
    ExerciseMuscle,
    MuscleGroupMember,
)

REVISION = "a" * 40
OTHER_REVISION = "b" * 40


def snapshot(**overrides) -> dict:
    return {"exercises": [{"id": "import-test", "name_en": "Test", **overrides}]}


@pytest.fixture
def catalog(db: Session):  # noqa: ANN201
    """Own only synthetic records; preserve the shared seeded catalog."""
    from verve_backend.core.db import get_engine

    with Session(get_engine(rls=False)) as session:
        yield session
        session.rollback()
        for exercise in session.exec(
            select(Exercise).where(
                Exercise.source == "repdb", Exercise.source_id == "import-test"
            )
        ).all():
            for link in session.exec(
                select(ExerciseMuscle).where(ExerciseMuscle.exercise_id == exercise.id)
            ).all():
                session.delete(link)
            session.flush()
            session.delete(exercise)
        state = session.get(ExerciseCatalogImportState, "repdb")
        if state:
            session.delete(state)
        session.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": ""},
        {"name_en": " "},
        {"primary_muscles": "legs"},
        {"primary_muscles": ["a", "a"]},
        {"primary_muscles": ["a"], "secondary_muscles": ["a"]},
    ],
)
def test_invalid_snapshot(overrides) -> None:
    with pytest.raises(ValueError, match=r"nonempty|muscle"):
        validate_snapshot(snapshot(**overrides))


def test_duplicate_source_ids_rejected() -> None:
    data = snapshot()
    data["exercises"] *= 2
    with pytest.raises(ValueError, match="Duplicate exercise"):
        validate_snapshot(data)


def test_new_muscles_and_dry_run(catalog: Session) -> None:
    from verve_backend.models import Muscle

    data = validate_snapshot(snapshot(primary_muscles=["import-owned-muscle"]))
    proposed = import_repdb(catalog, data, REVISION, dry_run=True)
    assert proposed.created == proposed.muscles_created == 1
    assert not catalog.new
    assert not catalog.dirty
    assert (
        catalog.exec(select(Muscle).where(Muscle.code == "import-owned-muscle")).first()
        is None
    )
    imported = import_repdb(catalog, data, REVISION)
    assert imported.muscles_created == 1
    assert catalog.exec(
        select(Muscle).where(Muscle.code == "import-owned-muscle")
    ).one()
    catalog.rollback()


@pytest.mark.parametrize("failing_commit", [1, 2])
def test_commit_failure_preserves_checkpoint(
    catalog: Session, tmp_path: Path, mocker, failing_commit
) -> None:
    catalog.add(ExerciseCatalogImportState(source="repdb", completed_revision=REVISION))
    catalog.commit()
    mocker.patch.object(cli, "download", return_value=json.dumps(snapshot()).encode())
    commit = Session.commit
    calls = 0

    def fail_commit(session: Session) -> None:
        nonlocal calls
        calls += 1
        if calls == failing_commit:
            raise RuntimeError("commit failed")
        commit(session)

    patched = mocker.patch.object(Session, "commit", fail_commit)
    result = CliRunner().invoke(
        cli.main, ["--revision", OTHER_REVISION, "--translations-dir", str(tmp_path)]
    )
    mocker.stop(patched)
    assert result.exit_code != 0
    catalog.expire_all()
    state = catalog.get(ExerciseCatalogImportState, "repdb")
    assert state is not None
    assert state.completed_revision == (REVISION if failing_commit == 1 else None)
    if failing_commit == 1:
        assert (
            catalog.exec(
                select(Exercise).where(Exercise.source_id == "import-test")
            ).first()
            is None
        )
    else:
        assert "Database import succeeded" in result.output


def test_lock_and_pending_checkpoint_during_publication(
    catalog: Session, tmp_path: Path, mocker
) -> None:
    from sqlalchemy import text

    from verve_backend.core.db import get_engine

    mocker.patch.object(cli, "download", return_value=json.dumps(snapshot()).encode())
    replace = cli.os.replace

    def publish(source: Path, destination: Path) -> None:
        with get_engine(rls=False).connect() as connection:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": cli.LOCK_ID}
            ).scalar_one()
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": cli.LOCK_ID}
                )
            assert not acquired
        catalog.expire_all()
        state = catalog.get(ExerciseCatalogImportState, "repdb")
        assert state is not None
        assert state.completed_revision is None
        replace(source, destination)

    mocker.patch.object(cli.os, "replace", side_effect=publish)
    result = CliRunner().invoke(
        cli.main, ["--revision", REVISION, "--translations-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    with get_engine(rls=False).connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": cli.LOCK_ID}
        ).scalar_one()
        if acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": cli.LOCK_ID}
            )
        assert acquired


def test_reconcile_preserves_identity_and_updates_roles(catalog: Session) -> None:
    groups = {
        (m.group_id, m.muscle_id) for m in catalog.exec(select(MuscleGroupMember)).all()
    }
    first = import_repdb(
        catalog,
        validate_snapshot(snapshot(primary_muscles=["quadriceps", "hamstrings"])),
        REVISION,
    )
    exercise = catalog.exec(
        select(Exercise).where(Exercise.source_id == "import-test")
    ).one()
    identity = exercise.id
    exercise.code = "local-import-test"
    exercise.is_active = False
    second = import_repdb(
        catalog,
        validate_snapshot(snapshot(secondary_muscles=["quadriceps"])),
        OTHER_REVISION,
    )
    assert exercise.id == identity
    assert exercise.code == "local-import-test"
    assert not exercise.is_active
    links = catalog.exec(
        select(ExerciseMuscle).where(ExerciseMuscle.exercise_id == identity)
    ).all()
    assert [(link.muscle.code, link.role) for link in links] == [
        ("quadriceps", "secondary")
    ]
    assert first.created == 1
    assert second.names["en"] == {"local-import-test": "Test"}
    assert (
        import_repdb(
            catalog,
            validate_snapshot(snapshot(secondary_muscles=["quadriceps"])),
            OTHER_REVISION,
        ).unchanged
        == 1
    )
    import_repdb(catalog, [], REVISION)
    assert exercise.source_revision == OTHER_REVISION
    assert {
        (m.group_id, m.muscle_id) for m in catalog.exec(select(MuscleGroupMember)).all()
    } == groups


@pytest.mark.parametrize("repair", ["force", "missing", "stale", "pending", "absent"])
def test_head_and_output_repairs(
    catalog: Session, tmp_path: Path, mocker, repair
) -> None:
    def upstream(url: str) -> bytes:
        if url.endswith("commits/HEAD"):
            return json.dumps({"sha": REVISION}).encode()
        assert f"/{REVISION}/exercises.json" in url
        return json.dumps(snapshot()).encode()

    download = mocker.patch.object(cli, "download", side_effect=upstream)
    args = ["--translations-dir", str(tmp_path)]
    runner = CliRunner()
    result = runner.invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    download.reset_mock()
    if repair == "missing":
        (tmp_path / "en.json").unlink()
    elif repair == "stale":
        (tmp_path / "en.json").write_text('{"exercises":{"import-test":"Edit"}}')
    elif repair in ("pending", "absent"):
        state = catalog.get(ExerciseCatalogImportState, "repdb")
        assert state is not None
        if repair == "pending":
            state.completed_revision = None
        else:
            catalog.delete(state)
        catalog.commit()
    else:
        args.append("--force")
    repaired = runner.invoke(cli.main, args)
    assert repaired.exit_code == 0, repaired.output
    assert json.loads(repaired.output)["status"] == "imported"
    assert download.call_count == 2


def test_download_failure_keeps_checkpoint(
    catalog: Session, tmp_path: Path, mocker
) -> None:
    catalog.add(ExerciseCatalogImportState(source="repdb", completed_revision=REVISION))
    catalog.commit()
    mocker.patch.object(cli, "download", side_effect=OSError("offline"))
    result = CliRunner().invoke(cli.main, ["--translations-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "offline" in result.output
    catalog.expire_all()
    state = catalog.get(ExerciseCatalogImportState, "repdb")
    assert state is not None
    assert state.completed_revision == REVISION


def test_invalid_later_input_keeps_database(
    catalog: Session, tmp_path: Path, mocker
) -> None:
    data = snapshot()
    data["exercises"].append({"id": "invalid"})
    mocker.patch.object(cli, "download", return_value=json.dumps(data).encode())
    result = CliRunner().invoke(
        cli.main, ["--revision", REVISION, "--translations-dir", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert (
        catalog.exec(
            select(Exercise).where(Exercise.source_id == "import-test")
        ).first()
        is None
    )
    assert catalog.get(ExerciseCatalogImportState, "repdb") is None


def test_collision_rolls_back(catalog: Session) -> None:
    with pytest.raises(ValueError, match="collision"), catalog.begin_nested():
        import_repdb(
            catalog,
            validate_snapshot(
                {
                    "exercises": [
                        {"id": "import-test", "name_en": "OK"},
                        {"id": "squat", "name_en": "Collision"},
                    ]
                }
            ),
            REVISION,
        )
    assert (
        catalog.exec(
            select(Exercise).where(Exercise.source_id == "import-test")
        ).first()
        is None
    )
    assert (
        catalog.exec(select(Exercise).where(Exercise.code == "squat")).one().source
        == "test"
    )


def test_local_cli_merges_and_dry_run(catalog: Session, tmp_path: Path, mocker) -> None:
    network = mocker.patch.object(
        cli, "download", side_effect=AssertionError("local input used network")
    )
    source = tmp_path / "source.json"
    source.write_text(json.dumps(snapshot()))
    output = tmp_path / "names"
    args = [
        "--input",
        str(source),
        "--revision",
        REVISION,
        "--translations-dir",
        str(output),
    ]
    runner = CliRunner()
    dry = runner.invoke(cli.main, [*args, "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert not output.exists()
    assert catalog.get(ExerciseCatalogImportState, "repdb") is None
    output.mkdir()
    original = {
        "other": "kept",
        "exercises": {"import-test": "Alt", "absent": "Bleibt"},
    }
    (output / "de.json").write_text(json.dumps(original))
    result = runner.invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert json.loads((output / "de.json").read_text()) == original
    assert json.loads((output / "en.json").read_text())["exercises"] == {
        "import-test": "Test"
    }
    network.assert_not_called()


def test_cli_skip_and_publication_repair(
    catalog: Session, tmp_path: Path, mocker
) -> None:
    download = mocker.patch.object(
        cli, "download", return_value=json.dumps(snapshot()).encode()
    )
    runner = CliRunner()
    args = ["--revision", REVISION, "--translations-dir", str(tmp_path)]
    result = runner.invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    download.reset_mock()
    before = (tmp_path / "en.json").stat().st_mtime_ns
    assert json.loads(runner.invoke(cli.main, args).output)["status"] == "unchanged"
    download.assert_not_called()
    assert (tmp_path / "en.json").stat().st_mtime_ns == before
    replace = mocker.patch.object(cli.os, "replace", side_effect=OSError("disk"))
    failed = runner.invoke(
        cli.main, ["--revision", OTHER_REVISION, "--translations-dir", str(tmp_path)]
    )
    assert failed.exit_code != 0
    assert "Database import succeeded" in failed.output
    catalog.expire_all()
    state = catalog.get(ExerciseCatalogImportState, "repdb")
    assert state is not None
    assert state.completed_revision is None
    mocker.stop(replace)
    repaired = runner.invoke(cli.main, args)
    assert repaired.exit_code == 0, repaired.output
    assert json.loads(repaired.output)["status"] == "imported"
