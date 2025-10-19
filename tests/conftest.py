import os
from typing import Generator

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
        # generate_data(session)
        yield session


@pytest.fixture(scope="session", autouse=True)
def object_store():  # noqa: ANN201
    from verve_backend.api.deps import get_and_init_s3_client

    return get_and_init_s3_client()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    from verve_backend.core.config import settings
    from verve_backend.main import app

    assert settings.ENVIRONMENT == "testing"

    with TestClient(
        app,
        base_url=f"http://testserver{settings.API_V1_STR}",
    ) as c:
        yield c
