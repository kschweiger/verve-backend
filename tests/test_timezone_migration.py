from collections.abc import Generator
from datetime import UTC, date, datetime
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

TIMESTAMP_COLUMNS = {
    "activities": (("start", False), ("created_at", False)),
    "activity_collections": (("created_at", False), ("updated_at", False)),
    "goals": (("current_updated", True), ("created_at", False)),
    "locations": (("created_at", False),),
    "password_reset_tokens": (
        ("expires_at", False),
        ("used_at", True),
        ("created_at", False),
    ),
    "track_points": (("time", True),),
    "zone_intervals": (("created_at", False),),
}


@pytest.fixture(scope="session", autouse=True)
def db() -> None:
    """Use temporary legacy tables instead of the shared application fixture."""


@pytest.fixture
def revision() -> ModuleType:
    return ScriptDirectory("alembic").get_revision("d9e3386babd7").module


@pytest.fixture
def legacy_connection() -> Generator[Connection]:
    from verve_backend.core.db import get_engine

    with get_engine().connect() as connection, connection.begin():
        # Never let an unqualified migration operation reach application tables.
        connection.execute(sa.text("SET LOCAL search_path TO pg_temp"))
        metadata = sa.MetaData()
        for table_name, columns in TIMESTAMP_COLUMNS.items():
            sa.Table(
                table_name,
                metadata,
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Uuid(), nullable=False),
                *(
                    sa.Column(name, sa.DateTime(), nullable=nullable)
                    for name, nullable in columns
                ),
                prefixes=["TEMPORARY"],
                postgresql_on_commit="DROP",
            )
        sa.Table(
            "user_settings",
            metadata,
            sa.Column("user_id", sa.Uuid(), primary_key=True),
            prefixes=["TEMPORARY"],
            postgresql_on_commit="DROP",
        )
        sa.Table(
            "equipment",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_date", sa.DateTime(), nullable=True),
            prefixes=["TEMPORARY"],
            postgresql_on_commit="DROP",
        )
        metadata.create_all(connection, checkfirst=False)
        for table_name, columns in TIMESTAMP_COLUMNS.items():
            for row_id, month in ((1, 1), (2, 7), (3, 1)):
                connection.execute(
                    metadata.tables[table_name].insert(),
                    {
                        "id": row_id,
                        "user_id": "00000000-0000-0000-0000-000000000001",
                        **{
                            name: None
                            if row_id == 3 and nullable
                            else datetime(2026, month, 1, 12, 34, 56, 123456)
                            for name, nullable in columns
                        },
                    },
                )
        connection.execute(
            metadata.tables["user_settings"].insert(),
            {"user_id": "00000000-0000-0000-0000-000000000001"},
        )
        connection.execute(
            metadata.tables["equipment"].insert(),
            [
                {"id": 1, "purchase_date": datetime(2026, 7, 1, 23, 45)},
                {"id": 2, "purchase_date": None},
            ],
        )
        yield connection
        # PostgreSQL rolls back the temporary tables as well as the changes.
        connection.rollback()


def migrate(connection: Connection, revision: ModuleType, direction: str) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        getattr(revision, direction)()


def test_timezone_upgrade_backfills_required_fields(
    legacy_connection: Connection, revision: ModuleType
) -> None:
    migrate(legacy_connection, revision, "upgrade")

    for table_name in ("activities", "user_settings"):
        zones = (
            legacy_connection.execute(sa.text(f"SELECT timezone FROM {table_name}"))
            .scalars()
            .all()
        )
        assert zones
        assert set(zones) == {"Europe/Berlin"}
        columns = sa.inspect(legacy_connection).get_columns(table_name)
        timezone = next(column for column in columns if column["name"] == "timezone")
        assert timezone["nullable"] is False
        assert timezone["default"] is None
        with pytest.raises(sa.exc.IntegrityError), legacy_connection.begin_nested():
            legacy_connection.execute(
                sa.text(f"UPDATE {table_name} SET timezone = NULL")
            )


@pytest.mark.parametrize("session_timezone", ["UTC", "America/Los_Angeles"])
def test_timestamps_convert_from_berlin_and_round_trip(
    legacy_connection: Connection, revision: ModuleType, session_timezone: str
) -> None:
    legacy_connection.execute(
        sa.text("SELECT set_config('TimeZone', :timezone, true)"),
        {"timezone": session_timezone},
    )
    migrate(legacy_connection, revision, "upgrade")

    for table_name, columns in TIMESTAMP_COLUMNS.items():
        for column_name, nullable in columns:
            timestamps = (
                legacy_connection.execute(
                    sa.text(f"SELECT {column_name} FROM {table_name} ORDER BY id")
                )
                .scalars()
                .all()
            )
            assert timestamps == [
                datetime(2026, 1, 1, 11, 34, 56, 123456, tzinfo=UTC),
                datetime(2026, 7, 1, 10, 34, 56, 123456, tzinfo=UTC),
                None
                if nullable
                else datetime(2026, 1, 1, 11, 34, 56, 123456, tzinfo=UTC),
            ], (table_name, column_name)

    migrate(legacy_connection, revision, "downgrade")
    for table_name, columns in TIMESTAMP_COLUMNS.items():
        for column_name, nullable in columns:
            timestamps = (
                legacy_connection.execute(
                    sa.text(f"SELECT {column_name} FROM {table_name} ORDER BY id")
                )
                .scalars()
                .all()
            )
            assert timestamps == [
                datetime(2026, 1, 1, 12, 34, 56, 123456),
                datetime(2026, 7, 1, 12, 34, 56, 123456),
                None if nullable else datetime(2026, 1, 1, 12, 34, 56, 123456),
            ], (table_name, column_name)
    assert all(
        column["name"] != "timezone"
        for table_name in ("activities", "user_settings")
        for column in sa.inspect(legacy_connection).get_columns(table_name)
    )


def test_purchase_date_conversion_preserves_calendar_date(
    legacy_connection: Connection, revision: ModuleType
) -> None:
    migrate(legacy_connection, revision, "upgrade")
    dates = (
        legacy_connection.execute(
            sa.text("SELECT purchase_date FROM equipment ORDER BY id")
        )
        .scalars()
        .all()
    )
    assert dates == [date(2026, 7, 1), None]

    migrate(legacy_connection, revision, "downgrade")
    timestamps = (
        legacy_connection.execute(
            sa.text("SELECT purchase_date FROM equipment ORDER BY id")
        )
        .scalars()
        .all()
    )
    assert timestamps == [datetime(2026, 7, 1), None]


def test_timezone_migration_preserves_activity_rls(
    legacy_connection: Connection, revision: ModuleType
) -> None:
    legacy_connection.execute(
        sa.text("ALTER TABLE activities ENABLE ROW LEVEL SECURITY")
    )
    legacy_connection.execute(
        sa.text(
            "CREATE POLICY activity_isolation_policy ON activities FOR ALL "
            "USING (user_id = current_setting('verve_user.curr_user')::uuid)"
        )
    )
    policy_query = sa.text(
        "SELECT polname, pg_get_expr(polqual, polrelid) FROM pg_policy "
        "WHERE polrelid = 'activities'::regclass"
    )
    original_policy = legacy_connection.execute(policy_query).one()

    for direction in ("upgrade", "downgrade"):
        migrate(legacy_connection, revision, direction)
        assert legacy_connection.execute(policy_query).one() == original_policy
        assert legacy_connection.execute(
            sa.text(
                "SELECT relrowsecurity FROM pg_class WHERE oid = 'activities'::regclass"
            )
        ).scalar_one()
