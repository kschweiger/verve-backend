import json
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from importlib.resources import files

import pytest
from click.testing import CliRunner
from sqlalchemy import Engine, MetaData, inspect, text
from sqlmodel import Session, SQLModel, select

from tests.test_exercise_catalog_data import document
from verve_backend.models import (
    Exercise,
    ExerciseCatalogSyncState,
    Muscle,
    MuscleGroup,
)

CATALOG_SCHEMA = "catalog_import_tests"
CATALOG_TABLES = (
    "exercises",
    "muscles",
    "muscle_groups",
    "exercise_muscles",
    "muscle_group_members",
    "exercise_catalog_sync_state",
)


@pytest.fixture(scope="session")
def catalog_metadata() -> MetaData:
    metadata = MetaData()
    for name in CATALOG_TABLES:
        SQLModel.metadata.tables[name].to_metadata(metadata)
    return metadata


@pytest.fixture(scope="session")
def catalog_engine(catalog_metadata: MetaData) -> Engine:
    from verve_backend.core.config import settings
    from verve_backend.core.db import get_engine

    assert settings.ENVIRONMENT == "testing"
    assert settings.POSTGRES_SCHEMA != CATALOG_SCHEMA
    engine = get_engine(rls=False).execution_options(
        schema_translate_map={None: CATALOG_SCHEMA}
    )
    if not inspect(engine).has_schema(CATALOG_SCHEMA):
        pytest.fail(
            f"Create the {CATALOG_SCHEMA!r} schema before running importer tests"
        )
    catalog_metadata.drop_all(engine)
    catalog_metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def db(
    catalog_engine: Engine, catalog_metadata: MetaData, mocker
) -> Generator[Session]:
    """Override the shared seeded database with an empty, isolated catalog."""
    mocker.patch("verve_backend.core.db.get_engine", return_value=catalog_engine)
    with catalog_engine.begin() as connection:
        for table in reversed(catalog_metadata.sorted_tables):
            connection.execute(table.delete())
    try:
        with Session(catalog_engine) as session:
            yield session
    finally:
        with catalog_engine.begin() as connection:
            for table in reversed(catalog_metadata.sorted_tables):
                connection.execute(table.delete())


@pytest.fixture
def catalog_db(db: Session) -> Session:
    return db


@pytest.fixture
def source(tmp_path):  # noqa: ANN201
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(document()))
    return path


def test_import_keeps_application_catalog_unchanged(catalog_engine, source) -> None:
    from verve_backend.cli import import_exercises as cli
    from verve_backend.core.config import settings

    application_engine = catalog_engine.execution_options(
        schema_translate_map={None: settings.POSTGRES_SCHEMA}
    )

    def application_catalog() -> dict:
        with application_engine.connect() as connection:
            existing = set(
                inspect(connection).get_table_names(schema=settings.POSTGRES_SCHEMA)
            )
            return {
                name: frozenset(
                    connection.execute(SQLModel.metadata.tables[name].select()).all()
                )
                for name in CATALOG_TABLES
                if name in existing
            }

    original = application_catalog()
    assert cli.run_import(source)["status"] == "imported"
    assert application_catalog() == original
    with catalog_engine.connect() as connection:
        assert set(
            connection.execute(
                text("SELECT code FROM catalog_import_tests.exercises")
            ).scalars()
        ) == {"test_squat", "test_unmapped"}


def test_reconcile_identity_roles_activation_and_groups(catalog_db, source) -> None:
    from verve_backend.core.exercise_catalog import sync_catalog
    from verve_backend.core.exercise_catalog_data import load_catalog

    session = catalog_db
    session.add(Muscle(code="quadriceps"))
    session.flush()
    first = sync_catalog(session, load_catalog(source))
    assert first.created == first.muscles_created == first.groups_created == 2
    exercise = session.exec(select(Exercise).where(Exercise.code == "test_squat")).one()
    group = session.exec(
        select(MuscleGroup).where(MuscleGroup.code == "test_legs")
    ).one()
    identity, group_id = exercise.id, group.id
    assert {g.code for g in session.exec(select(MuscleGroup)).all()} == {
        "test_legs",
        "test_empty",
    }
    raw = document()
    raw["exercises"][0].update(
        is_active=False, primary_muscles=["test_core"], secondary_muscles=[]
    )
    raw["muscle_groups"][0]["muscles"] = ["test_core"]
    raw["muscle_groups"][1]["muscles"] = ["test_core"]
    source.write_text(json.dumps(raw))
    changed = sync_catalog(session, load_catalog(source))
    session.expire_all()
    exercise = session.get(Exercise, identity)
    assert exercise is not None
    assert not exercise.is_active
    assert {(link.muscle.code, link.role.value) for link in exercise.muscle_links} == {
        ("test_core", "primary")
    }
    group = session.get(MuscleGroup, group_id)
    assert group is not None
    assert {link.muscle.code for link in group.members} == {"test_core"}
    assert changed.updated == 1
    assert sync_catalog(session, load_catalog(source)).unchanged == 2
    raw["exercises"] = []
    raw["muscle_groups"] = [{"code": "test_legs", "muscles": []}]
    source.write_text(json.dumps(raw))
    sync_catalog(session, load_catalog(source))
    session.expire_all()
    assert session.get(Exercise, identity) is not None
    assert session.get(MuscleGroup, group_id).members == []
    assert {g.code for g in session.exec(select(MuscleGroup)).all()} == {"test_legs"}


def test_preview_does_not_mutate_catalog(catalog_db, source) -> None:
    from verve_backend.core.exercise_catalog import sync_catalog
    from verve_backend.core.exercise_catalog_data import load_catalog

    group = MuscleGroup(code="existing_group")
    catalog_db.add(group)
    catalog_db.flush()
    result = sync_catalog(catalog_db, load_catalog(source), dry_run=True)
    assert result.created == 2
    assert result.muscles_created == 3
    assert result.groups_deleted == 1
    assert not catalog_db.new
    assert not catalog_db.dirty
    assert not catalog_db.deleted
    assert (
        catalog_db.exec(select(Exercise).where(Exercise.code == "test_squat")).first()
        is None
    )
    assert catalog_db.exec(select(MuscleGroup.id)).all() == [group.id]


def test_cli_checkpoint_force_and_version(catalog_db, source) -> None:
    from verve_backend.cli import import_exercises as cli
    from verve_backend.core.exercise_catalog_data import load_catalog

    runner = CliRunner()
    args = ["--input", str(source)]
    result = runner.invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "imported"
    state = catalog_db.get(ExerciseCatalogSyncState, "test_catalog")
    assert state.content_hash == load_catalog(source).content_hash
    assert state.sync_version == cli.SYNC_VERSION
    group = catalog_db.exec(
        select(MuscleGroup).where(MuscleGroup.code == "test_legs")
    ).one()
    group_id = group.id
    for link in group.members:
        catalog_db.delete(link)
    catalog_db.commit()
    assert json.loads(runner.invoke(cli.main, args).output)["status"] == "unchanged"
    forced = runner.invoke(cli.main, [*args, "--force"])
    assert forced.exit_code == 0, forced.output
    catalog_db.expire_all()
    assert catalog_db.get(MuscleGroup, group_id).members
    state = catalog_db.get(ExerciseCatalogSyncState, "test_catalog")
    state.sync_version = cli.SYNC_VERSION + 1
    catalog_db.commit()
    assert json.loads(runner.invoke(cli.main, args).output)["status"] == "imported"
    assert (
        json.loads(runner.invoke(cli.main, [*args, "--dry-run"]).output)["status"]
        == "dry_run"
    )


@pytest.mark.parametrize("catalog_code", ["test_catalog", "other_catalog"])
def test_failed_commit_rolls_back_data_and_checkpoint(
    catalog_db, source, mocker, catalog_code
) -> None:
    from verve_backend.cli import import_exercises as cli

    cli.run_import(source)
    state = catalog_db.get(ExerciseCatalogSyncState, "test_catalog")
    previous_hash = state.content_hash
    raw = document()
    raw["source"] = catalog_code
    raw["exercises"][0]["is_active"] = False
    raw["muscle_groups"] = []
    source.write_text(json.dumps(raw))
    catalog_db.rollback()
    patched = mocker.patch.object(
        Session, "commit", side_effect=RuntimeError("commit failed")
    )
    result = CliRunner().invoke(cli.main, ["--input", str(source)])
    mocker.stop(patched)
    assert result.exit_code != 0
    assert "commit failed" in result.output
    catalog_db.expire_all()
    assert (
        catalog_db.get(ExerciseCatalogSyncState, "test_catalog").content_hash
        == previous_hash
    )
    assert (
        catalog_db.exec(select(Exercise).where(Exercise.code == "test_squat"))
        .one()
        .is_active
    )
    assert catalog_db.exec(
        select(MuscleGroup).where(MuscleGroup.code == "test_legs")
    ).one()
    assert cli.run_import(source)["status"] == "imported"


def test_transaction_lock_and_release(catalog_db, source, mocker) -> None:
    from verve_backend.cli import import_exercises as cli
    from verve_backend.core.db import get_engine

    original = cli.sync_catalog

    def observe(*args, **kwargs):
        with get_engine(rls=False).connect() as connection:
            assert not connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": cli.LOCK_ID}
            ).scalar_one()
        return original(*args, **kwargs)

    mocker.patch.object(cli, "sync_catalog", side_effect=observe)
    cli.run_import(source)
    with get_engine(rls=False).connect() as connection:
        assert connection.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": cli.LOCK_ID}
        ).scalar_one()


def test_concurrent_starts_serialize(catalog_db, source) -> None:
    from verve_backend.cli import import_exercises as cli

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cli.run_import, [source, source]))
    assert sorted(item["status"] for item in results) == ["imported", "unchanged"]


def test_invalid_input_before_database(catalog_db, source, mocker) -> None:
    from verve_backend.cli import import_exercises as cli

    cli.run_import(source)
    raw = document()
    raw["exercises"].append(
        {"code": "bad", "primary_muscles": ["missing"], "secondary_muscles": []}
    )
    source.write_text(json.dumps(raw))
    connection = mocker.patch(
        "verve_backend.core.db.get_engine",
        side_effect=AssertionError("database opened"),
    )
    result = CliRunner().invoke(cli.main, ["--input", str(source)])
    assert result.exit_code != 0
    connection.assert_not_called()


def test_default_bundle_from_other_directory_leaves_locales_unchanged(
    catalog_db, tmp_path, monkeypatch
) -> None:
    from verve_backend.cli import import_exercises as cli

    locales = files("verve_backend").joinpath("locales")
    before = {
        lang: locales.joinpath(f"{lang}.json").read_bytes() for lang in ("en", "de")
    }
    monkeypatch.chdir(tmp_path)
    assert cli.run_import()["status"] == "imported"
    assert cli.run_import()["status"] == "unchanged"
    assert cli.run_import(dry_run=True)["status"] == "dry_run"
    assert not list(tmp_path.iterdir())
    assert all(
        locales.joinpath(f"{lang}.json").read_bytes() == content
        for lang, content in before.items()
    )


@pytest.mark.parametrize("option", ["--revision", "--translations-dir"])
def test_unknown_cli_options(option) -> None:
    from verve_backend.cli import import_exercises as cli

    assert CliRunner().invoke(cli.main, [option, "unused"]).exit_code == 2


def test_switching_catalogs_reapplies_global_groups(catalog_db, source) -> None:
    from verve_backend.cli import import_exercises as cli

    cli.run_import(source)
    other = document()
    other["source"] = "other_catalog"
    other["muscle_groups"] = [{"code": "test_other", "muscles": ["test_core"]}]
    other_path = source.with_name("other.json")
    other_path.write_text(json.dumps(other))
    assert cli.run_import(other_path, dry_run=True)["status"] == "dry_run"
    assert cli.run_import(source)["status"] == "unchanged"
    cli.run_import(other_path)
    assert cli.run_import(source)["status"] == "imported"
    catalog_db.expire_all()
    assert {g.code for g in catalog_db.exec(select(MuscleGroup)).all()} == {
        "test_legs",
        "test_empty",
    }
    assert {
        s.catalog_code for s in catalog_db.exec(select(ExerciseCatalogSyncState)).all()
    } == {"test_catalog"}
