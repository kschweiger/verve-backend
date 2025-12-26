import logging
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

from geo_track_analyzer import PyTrack
from rich.console import Console
from sqlalchemy import text

from verve_backend import crud, models
from verve_backend.api.deps import get_db, get_user_session
from verve_backend.core.config import settings
from verve_backend.models import (
    UserBase,
    UserCreate,
    UserPublic,
)
from verve_backend.tasks import process_activity_highlights

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rls_tester")


console = Console()


def find_all_relevant_tables() -> list[str]:
    with contextmanager(get_db)() as session:
        tables = session.exec(
            text(
                f"""
                SELECT
                    table_name
                FROM
                    information_schema.columns
                WHERE
                    table_schema = '{settings.POSTGRES_SCHEMA}'
                    AND column_name = 'user_id'
                ORDER BY
                    table_name;
                """
            )  # type: ignore
        ).all()
    table_names = []
    for (name,) in tables:
        if name in [
            "user_settings",  # Gets filled with user creation
        ]:
            continue
        table_names.append(name)

    return table_names


def create_users() -> tuple[models.UserPublic, models.UserPublic]:
    """Create two users for testing."""
    with contextmanager(get_db)() as session:
        user_a_in = UserCreate(
            email=f"rls_test_a_{uuid.uuid4()}@example.com",
            name=f"UserA_{uuid.uuid4().hex[:6]}",
            password="password123",
            full_name="RLS Test User A",
        )
        user_b_in = UserCreate(
            email=f"rls_test_b_{uuid.uuid4()}@example.com",
            name=f"UserB_{uuid.uuid4().hex[:6]}",
            password="password123",
            full_name="RLS Test User B",
        )

        # We use crud to ensure side effects (like UserSettings creation) happen
        res_a = crud.create_user(session=session, user_create=user_a_in)
        res_b = crud.create_user(session=session, user_create=user_b_in)
        user_a, user_b = res_a.unwrap(), res_b.unwrap()

        return UserPublic.model_validate(user_a), UserPublic.model_validate(user_b)


def create_user_data(user: UserBase) -> None:
    with contextmanager(get_user_session)(user=user) as (user_id, session):  # type: ignore
        activity_1 = crud.create_activity(
            session=session,
            create=models.ActivityCreate(
                start=datetime.now(),
                duration=timedelta(days=0, seconds=60 * 60 * 2),
                distance=10.0,
                type_id=1,
                sub_type_id=1,
                name=None,
            ),
            user=user,  # type: ignore
        ).unwrap()

        now = datetime.now()
        track = PyTrack(
            points=[(1, 1), (1.0001, 1.0001), (1.0002, 1.0002), (1.0003, 1.0003)],
            elevations=[100, 105, 110, 110],
            times=[
                now,
                now + timedelta(seconds=30),
                now + timedelta(seconds=60),
                now + timedelta(seconds=90),
            ],
            extensions={
                "heart_rate": [120, 130, 140, 140],
                "power": [150, 160, 170, 170],
            },
        )
        crud.insert_track(
            session=session,
            track=track,
            activity_id=activity_1.id,
            user_id=user_id,
            batch_size=500,
        )
        crud.update_activity_with_track_data(
            session=session,
            activity_id=activity_1.id,
            track=track,
        )
        process_activity_highlights(activity_1.id, uuid.UUID(user_id))

        crud.create_location(
            session=session,
            user_id=uuid.UUID(user_id),
            data=models.LocationCreate(
                name="Some location",
                latitude=1,
                longitude=1,
            ),
        )

        equipment_1 = crud.create_equipment(
            session=session,
            data=models.EquipmentCreate(
                name="Basic Bike",
                equipment_type=models.EquipmentType.BIKE,
            ),
            user_id=user_id,
        ).unwrap()

        equipment_set = crud.create_equipment_set(
            session=session,
            name="Basic Set",
            data=[equipment_1],
            user_id=uuid.UUID(user_id),
        ).unwrap()

        crud.put_default_equipment_set(
            session=session,
            user_id=uuid.UUID(user_id),
            set_id=equipment_set.id,
            activity_type_id=1,
            activity_sub_type_id=1,
        )
        goal_0 = crud.create_goal(  # noqa: F841
            user_id=user_id,
            session=session,
            goal=models.GoalCreate(
                name="Fix Month Goal 0",
                temporal_type=models.TemporalType.MONTHLY,
                year=now.year,
                month=1,
                target=200,
                type=models.GoalType.MANUAL,
                aggregation=models.GoalAggregation.COUNT,
            ),
        ).unwrap()
        session.add_all(
            [
                models.ZoneInterval(
                    name="Zone 1",
                    metric="heart_rate",
                    start=None,
                    end=100,
                    user_id=uuid.UUID(user_id),
                    color="#FF0000",
                ),
                models.ZoneInterval(
                    name="Zone 2",
                    metric="heart_rate",
                    start=100,
                    end=150,
                    user_id=uuid.UUID(user_id),
                    color="#00FF00",
                ),
                models.ZoneInterval(
                    name="Zone 3",
                    metric="heart_rate",
                    start=150,
                    end=None,
                    user_id=uuid.UUID(user_id),
                    color="#0000FF",
                ),
            ]
        )
        session.commit()

        session.exec(
            text(
                f"""
                INSERT INTO {settings.POSTGRES_SCHEMA}.image
                    (id, user_id, activity_id)
                VALUES (
                    '{uuid.uuid4()}',
                    '{user_id}',
                    '{activity_1.id}'
                )
                """
            )  # type: ignore
        )
        session.exec(
            text(
                f"""
                INSERT INTO {settings.POSTGRES_SCHEMA}.raw_track_data
                    (store_path, user_id, activity_id)
                VALUES (
                    'blubb',
                    '{user_id}',
                    '{activity_1.id}'
                )
                """
            )  # type: ignore
        )
        session.commit()


def check_tables(user: UserPublic, tables: list[str], exp_data: bool) -> bool:
    overall_success = True
    with contextmanager(get_user_session)(user=user) as (_, session):  # type: ignore
        for name in tables:
            stmt = text(f"SELECT * FROM {name}")
            data = session.exec(stmt).all()  # type: ignore
            success = len(data) > 0 if exp_data else len(data) == 0

            overall_success = overall_success and success
            if success:
                console.print(
                    f"[green][PASS][/green] Table '{name}' for user '{user.name}'"
                )
            else:
                console.print(
                    f"[red][FAIL][/red] Table '{name}' for user '{user.name}'"
                )

    if overall_success:
        console.print(f"[green]All RLS checks passed for user '{user.name}'[/green]")
    else:
        console.print(f"[red]Some RLS checks failed for user '{user.name}'[/red]")

    return overall_success


def main() -> None:
    user_a, user_b = create_users()
    create_user_data(user_a)
    tables = find_all_relevant_tables()
    console.print(f"Found {len(tables)} relevant tables with user_id column.")
    console.print("Running test with user A (should see data)...")
    user_a_check = check_tables(user_a, tables, exp_data=True)
    console.print("Running test with user B (should see no data)...")
    user_b_check = check_tables(user_b, tables, exp_data=False)

    if user_a_check and user_b_check:
        console.print("[bold green]RLS verification successful![/bold green]")
        sys.exit(0)
    else:
        console.print("[bold red]RLS verification failed![/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
