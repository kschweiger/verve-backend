import os
import random
from datetime import datetime, timedelta
from importlib import resources
from typing import Any, Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from geo_track_analyzer import FITTrack, GPXFileTrack, PyTrack, Track
from sqlmodel import Session, SQLModel

from verve_backend.models import User


# This runs right after cmd arg parsing but after imports
# so the app cannot be imported in the global scope otherwise
# the settings cannot be overwritten with environ
def pytest_configure(config) -> None:
    os.environ["ENVIRONMENT"] = "testing"


@pytest.fixture(scope="session", autouse=True)
def db():  # noqa: ANN201
    from verve_backend import models  # noqa: F401
    from verve_backend.core.db import get_engine

    engine = get_engine(echo=False, rls=False)

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        generate_data(session)
        yield session


@pytest.fixture(scope="session")
def user2_token(client: TestClient) -> str:
    response = client.post(
        "/login/access-token",
        data={"username": "user2@mail.com", "password": "12345678"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest.fixture(scope="session")
def user1_token(client: TestClient) -> str:
    response = client.post(
        "/login/access-token",
        data={"username": "user1@mail.com", "password": "12345678"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest.fixture(scope="session")
def user1_id(client: TestClient, user1_token: str) -> UUID:
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    return data["id"]


@pytest.fixture
def temp_user_id() -> Generator[UUID, Any, Any]:
    from verve_backend import (
        crud,
    )
    from verve_backend.core.db import get_engine
    from verve_backend.models import User, UserCreate, UserSettings

    engine = get_engine(echo=False, rls=False)

    random_suffix = random.randint(100000, 999999)
    _user = UserCreate(
        name=f"temp_user_{random_suffix}",
        email=f"temp_{random_suffix}@user.mail",
        full_name="Temp User",
        password="temporarypassword",
    )
    with Session(engine) as session:
        result = crud.create_user(session=session, user_create=_user)
        user = result.unwrap()
        id = user.id
    yield id

    with Session(engine) as session:
        settings = session.get(UserSettings, id)
        user = session.get(User, id)
        session.delete(settings)
        session.delete(user)
        session.commit()


@pytest.fixture
def temp_user_token(temp_user_id: UUID, client: TestClient) -> str:
    from sqlmodel import Session

    from verve_backend.core.db import get_engine
    from verve_backend.models import User

    engine = get_engine(echo=False, rls=False)

    with Session(engine) as session:
        user = session.get(User, temp_user_id)
        if not user:
            raise ValueError(f"User with id {temp_user_id} not found")

        token = client.post(
            "/login/access-token",
            data={"username": user.email, "password": "temporarypassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).json()["access_token"]

    return token


@pytest.fixture
def celery_eager(monkeypatch) -> None:
    """
    A pytest fixture that forces Celery to run tasks synchronously (eagerly)
    for the duration of a single test by directly patching the existing
    Celery app configuration object in memory.

    This works even with a session-scoped TestClient.
    """
    from verve_backend.celery_app import celery as celery_app_instance

    # Use monkeypatch to temporarily set 'task_always_eager' to True.
    # The original value will be automatically restored after the test.
    monkeypatch.setattr(celery_app_instance.conf, "task_always_eager", True)


@pytest.fixture
def dummy_track() -> PyTrack:
    start_time = datetime(2024, 1, 15, 10, 0, 0)
    # Generate 122 points (one every 30 seconds for 61 minutes)
    num_points = 122
    points = []
    elevations = []
    times = []
    heartrates = []
    powers = []
    cadences = []
    temperatures = []

    base_lat, base_lon = 48.1351, 11.5820
    for i in range(num_points):
        # Simulate a cycling route with gradual position changes (~25 km/h average)
        points.append((base_lat + i * 0.0015, base_lon + i * 0.0015))
        # Varying elevation with some climbing
        elevations.append(520.0 + (i % 20) * 2.0 + (i // 40) * 10.0)
        times.append(start_time + timedelta(seconds=i * 30))
        # Realistic cycling metrics
        heartrates.append(120 + (i % 30) + (i // 60) * 5)
        powers.append(180 + (i % 40) * 2 + (i // 50) * 10)
        cadences.append(85 + (i % 10))
        temperatures.append(18.5 + (i / num_points) * 2.0)

    track = PyTrack(
        points=points,
        elevations=elevations,
        times=times,
        extensions={
            "heartrate": heartrates,
            "power": powers,
            "cadence": cadences,
            "temperature": temperatures,
        },
    )
    return track


@pytest.fixture(scope="session", autouse=True)
def object_store():  # noqa: ANN201
    from verve_backend.api.deps import get_and_init_s3_client

    return get_and_init_s3_client()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    from verve_backend.core.config import settings
    from verve_backend.main import app

    assert settings.ENVIRONMENT == "testing"

    with TestClient(
        app,
        base_url=f"http://testserver{settings.API_V1_STR}",
    ) as c:
        yield c


@pytest.fixture
def create_dummy_activity(
    session: Session,
    user_id: UUID,
    start: datetime,
    distance: float,
    type_id: int = 1,
    track: Track | None = None,
    name: str | None = None,
) -> Any:
    """Creates a simple activity, saves it to the DB, and returns it."""
    from verve_backend.api.common.track import update_activity_with_track
    from verve_backend.crud import insert_track
    from verve_backend.models import Activity

    activity = Activity(
        user_id=user_id,
        start=start,
        distance=distance,
        duration=timedelta(minutes=60),
        type_id=type_id,
        sub_type_id=None,
        name=f"Test Activity {distance}km" if name is None else name,
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)

    if track:
        insert_track(
            session=session,
            track=track,
            activity_id=activity.id,
            user_id=user_id,
        )
        update_activity_with_track(activity=activity, track=track)

        overview = track.get_track_overview()
        activity.distance = overview.moving_distance_km
        session.add(activity)
        session.commit()
        session.refresh(activity)

    return activity


def generate_data(session: Session) -> None:
    from verve_backend import (
        crud,
        models,
    )
    from verve_backend.cli.setup_db import (
        setup_activity_types,
        setup_rls_policies,
    )
    from verve_backend.core.meta_data import LapData, SwimmingMetaData, SwimStyle
    from verve_backend.tasks import process_activity_highlights

    setup_activity_types(session)
    setup_rls_policies(session, "verve_testing")
    # --------------------- USERS ------------------------------
    created_users: list[User] = []
    for name, pw, email, full_name in [
        ("username1", "12345678", "user1@mail.com", "User Name"),
        ("username2", "12345678", "user2@mail.com", None),
    ]:
        created_users.append(
            crud.create_user(
                session=session,
                user_create=models.UserCreate(
                    name=name,
                    password=pw,
                    email=email,
                    full_name=full_name,
                ),
            ).unwrap()
        )

    # -------------------- ACTIVITIES ---------------------------
    activity_1 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=1, hour=12),
            duration=timedelta(days=0, seconds=60 * 60 * 2),
            distance=10.0,
            type_id=1,
            sub_type_id=1,
            name=None,
        ),
        user=created_users[0],  # type: ignore
    ).unwrap()

    resource_files = resources.files("tests.resources")

    track = FITTrack((resource_files / "MyWhoosh_1.fit").read_bytes())
    crud.insert_track(
        session=session,
        track=track,
        activity_id=activity_1.id,
        user_id=created_users[0].id,
        batch_size=500,
    )
    crud.update_activity_with_track_data(
        session=session,
        activity_id=activity_1.id,
        track=track,
    )
    process_activity_highlights(activity_1.id, created_users[0].id)

    activity_2 = crud.create_activity(  # noqa: F841
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=2, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=30.0,
            type_id=1,
            sub_type_id=2,
            name=None,
        ),
        user=created_users[1],  # type: ignore
    ).unwrap()

    activity_3 = crud.create_activity(  # noqa: F841
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=2, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=30.0,
            type_id=4,  # Should be swimming
            sub_type_id=2,
            name=None,
            meta_data=SwimmingMetaData(
                segments=[
                    LapData(
                        count=4,
                        lap_lengths=50,
                        duration=timedelta(minutes=20),
                        style=SwimStyle.FREESTYLE,
                    )
                ]
            ).model_dump(mode="json"),
        ),
        user=created_users[0],  # type: ignore
    ).unwrap()

    activity_4 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=7, day=9, hour=10),
            duration=timedelta(days=0, seconds=60 * 60 * 2),
            distance=10.0,
            type_id=1,
            sub_type_id=1,
            name="Mont Venntoux Ride",
        ),
        user=created_users[1],  # type: ignore
    ).unwrap()

    track = GPXFileTrack(resource_files / "mont_ventoux.gpx")  # type: ignore
    crud.insert_track(
        session=session,
        track=track,
        activity_id=activity_4.id,
        user_id=created_users[1].id,
        batch_size=500,
    )
    crud.update_activity_with_track_data(
        session=session,
        activity_id=activity_4.id,
        track=track,
    )

    process_activity_highlights(activity_4.id, created_users[1].id)

    crud.create_location(
        session=session,
        user_id=created_users[1].id,
        data=models.LocationCreate(
            name="Mont Vontoux",
            latitude=44.17349080796914,
            longitude=5.277152032653785,
        ),
    )

    # ------------------------------- EQUIPMENT & SETS ---------------------------
    equipment_1 = crud.create_equipment(
        session=session,
        data=models.EquipmentCreate(
            name="Basic Bike",
            equipment_type=models.EquipmentType.BIKE,
        ),
        user_id=created_users[0].id,
    ).unwrap()
    equipment_2 = crud.create_equipment(
        session=session,
        data=models.EquipmentCreate(
            name="Basic Shoes",
            equipment_type=models.EquipmentType.SHOES,
        ),
        user_id=created_users[0].id,
    ).unwrap()

    equipment_set = crud.create_equipment_set(
        session=session,
        name="Basic Set",
        data=[equipment_1, equipment_2],
        user_id=created_users[0].id,
    ).unwrap()

    crud.put_default_equipment_set(
        session=session,
        user_id=created_users[0].id,
        set_id=equipment_set.id,
        activity_type_id=1,
        activity_sub_type_id=1,
    )

    # ------------------------------- GOALS ---------------------------
    goal_0 = crud.create_goal(  # noqa: F841
        user_id=created_users[0].id,
        session=session,
        goal=models.GoalCreate(
            name="Fix Month Goal 0",
            temporal_type=models.TemportalType.MONTHLY,
            year=2024,
            month=1,
            target=200,
            type=models.GoalType.MANUAL,
            aggregation=models.GoalAggregation.COUNT,
        ),
    ).unwrap()
    goal_1 = crud.create_goal(  # noqa: F841
        user_id=created_users[0].id,
        session=session,
        goal=models.GoalCreate(
            name="Yearly Goal",
            temporal_type=models.TemportalType.YEARLY,
            year=2025,
            target=1000,
            type=models.GoalType.ACTIVITY,
            aggregation=models.GoalAggregation.TOTAL_DISTANCE,
        ),
    ).unwrap()
    goal_2 = crud.create_goal(  # noqa: F841
        user_id=created_users[0].id,
        session=session,
        goal=models.GoalCreate(
            name="Fixed Month Goal",
            temporal_type=models.TemportalType.MONTHLY,
            year=2025,
            month=2,
            target=10,
            type=models.GoalType.ACTIVITY,
            aggregation=models.GoalAggregation.DURATION,
        ),
    ).unwrap()
