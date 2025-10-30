import os
from datetime import datetime, timedelta
from typing import Any, Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel


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


@pytest.fixture
def temp_user_id() -> Generator[UUID, Any, Any]:
    from verve_backend import (
        crud,
    )
    from verve_backend.core.db import get_engine
    from verve_backend.models import User, UserCreate, UserSettings

    engine = get_engine(echo=False, rls=False)

    _user = UserCreate(
        name="temp_user",
        email="temp@user.mail",
        full_name="Temp User",
        password="temporarypassword",
    )
    with Session(engine) as session:
        user = crud.create_user(session=session, user_create=_user)
        id = user.id
    yield id

    with Session(engine) as session:
        settings = session.get(UserSettings, id)
        user = session.get(User, id)
        session.delete(settings)
        session.delete(user)
        session.commit()


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


def generate_data(session: Session) -> None:
    from verve_backend import (
        crud,
        models,
    )
    from verve_backend.cli.setup_db import setup_db

    setup_db(session, "verve_testing")
    created_users = []
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
            )
        )
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
        user=created_users[0],
    )

    activity_2 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=2, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=30.0,
            type_id=1,
            sub_type_id=2,
            name=None,
        ),
        user=created_users[1],
    )
