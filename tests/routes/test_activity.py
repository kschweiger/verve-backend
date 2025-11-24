from datetime import datetime, timedelta
from importlib import resources

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pytest_mock import MockerFixture
from sqlmodel import Session, select

from verve_backend.core.meta_data import LapData, SwimmingMetaData, SwimStyle
from verve_backend.models import (
    ActivitiesPublic,
    ActivityCreate,
    ActivityHighlight,
    ActivityPublic,
    ActivityType,
    UserPublic,
)


def test_get_activities(client: TestClient, user1_token: str) -> None:
    response = client.get(
        "/activity",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
    data = ActivitiesPublic.model_validate(response.json())
    assert len(data.data) >= 1

    read_test_id = data.data[0].id
    response = client.get(
        f"/activity/{read_test_id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("params", "name", "type_id", "exp_name"),
    [
        ({}, None, 1, "Morning Ride"),
        ({}, None, 3, "Morning Activity"),
        ({"locale": "en"}, None, 1, "Morning Ride"),
        ({"locale": "de"}, "Schöne Ausfahrt", 1, "Schöne Ausfahrt"),
    ],
)
def test_create_activity_wo_name(
    client: TestClient,
    user1_token: str,
    params: dict[str, str],
    name: str | None,
    type_id: int,
    exp_name: str,
) -> None:
    activity_create = ActivityCreate(
        start=datetime(2024, 1, 1, 10),
        duration=timedelta(minutes=30),
        distance=1.0,
        moving_duration=timedelta(minutes=25),
        type_id=type_id,
        sub_type_id=None,
        name=name,
    )
    response = client.post(
        "/activity",
        json=activity_create.model_dump(exclude_unset=True, mode="json"),
        headers={"Authorization": f"Bearer {user1_token}"},
        params=params,
    )

    create_activity = ActivityPublic.model_validate(response.json())
    assert response.status_code == 200
    assert create_activity.name == exp_name


def test_auto_activity(
    mocker: MockerFixture,
    client: TestClient,
    user1_token: str,
) -> None:
    mock_delay = mocker.patch(
        "verve_backend.api.routes.activity.process_activity_highlights.delay"
    )
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user1_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
    )

    assert response.status_code == 200
    activity = ActivityPublic.model_validate(response.json())

    # Verify that activity was created with data from the FIT file
    assert activity.distance > 0
    assert activity.duration.total_seconds() > 0

    response_track = client.get(
        f"track/{activity.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response_track.status_code == 200
    raw_data = response_track.json()
    assert len(raw_data["data"]) > 0

    mock_delay.assert_called_once()
    call_args, _ = mock_delay.call_args

    # call_args is a tuple of the positional arguments: (activity_id, user_id)
    assert len(call_args) == 2
    assert call_args[0] == activity.id

    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {user1_token}"}
    )
    assert response.status_code == 200
    user = UserPublic.model_validate(response.json())

    assert call_args[1] == user.id


def test_auto_activity_e2e_with_eager_celery(
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    """
    An end-to-end test for the auto activity creation flow.

    By including the `celery_eager` fixture, we ensure that the highlight
    task runs immediately and blocks until completion before the API call returns.
    """
    # ARRANGE
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    # ACT: Call the API. The task will run synchronously in the same thread.
    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    # ASSERT: Check the database for the results of the now-completed task.
    # Note: We use db_session here, which is the transactional session, to ensure
    # we see the results of the API call's transaction.
    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    # Example of a more specific check
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is not None
    assert distance_highlight.value > 0


@pytest.mark.parametrize(
    ("update_data", "exp_values"),
    [
        (
            {"name": "new name"},
            {"name": "new name", "type_id": 1, "sub_type_id": 1, "meta_data": {}},
        ),
        (
            {"sub_type_id": None},
            {"name": "init name", "type_id": 1, "sub_type_id": None, "meta_data": {}},
        ),
        (
            {"sub_type_id": 2},
            {"name": "init name", "type_id": 1, "sub_type_id": 2, "meta_data": {}},
        ),
        (
            {"type_id": 2, "sub_type_id": 7},
            {"name": "init name", "type_id": 2, "sub_type_id": 7, "meta_data": {}},
        ),
        (
            {"meta_data": {"key": "value"}},
            {
                "name": "init name",
                "type_id": 1,
                "sub_type_id": 1,
                "meta_data": {"key": "value"},
            },
        ),
    ],
)
def test_update_activity(
    client: TestClient,
    user1_token: str,
    update_data: dict,
    exp_values: dict,
) -> None:
    activity_create = ActivityCreate(
        start=datetime(2024, 1, 1, 11),
        duration=timedelta(minutes=32),
        distance=1.0,
        type_id=1,
        sub_type_id=1,
        name="init name",
    )
    init_acticity = ActivityPublic.model_validate(
        client.post(
            "/activity",
            json=activity_create.model_dump(exclude_unset=True, mode="json"),
            headers={"Authorization": f"Bearer {user1_token}"},
        ).json()
    )

    response = client.patch(
        f"/activity/{init_acticity.id}",
        json=update_data,
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == 200

    final_activity = ActivityPublic.model_validate(
        client.get(
            f"activity/{init_acticity.id}",
            headers={"Authorization": f"Bearer {user1_token}"},
        ).json()
    )

    for key, value in exp_values.items():
        assert value == getattr(final_activity, key)


@pytest.mark.parametrize(
    ("update_data", "exp_status"),
    [
        ({"type_id": None}, 400),
        ({"sub_type_id": 7}, 400),
        ({"sub_type_id": 99999}, 404),
        ({"type_id": 2, "sub_type_id": 1}, 400),
        ({"type_id": 2}, 400),
        ({"name": None}, 400),
        ({"meta_data": None}, 400),
    ],
)
def test_update_activity_errors(
    client: TestClient,
    user1_token: str,
    update_data: dict,
    exp_status: int,
) -> None:
    activity_create = ActivityCreate(
        start=datetime(2024, 1, 1, 12),
        duration=timedelta(minutes=30),
        distance=1.0,
        type_id=1,
        sub_type_id=1,
        name="init name",
    )
    init_acticity = ActivityPublic.model_validate(
        client.post(
            "/activity",
            json=activity_create.model_dump(exclude_unset=True, mode="json"),
            headers={"Authorization": f"Bearer {user1_token}"},
        ).json()
    )

    response = client.patch(
        f"/activity/{init_acticity.id}",
        json=update_data,
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == exp_status


@pytest.mark.parametrize(
    ("activity_type_name", "meta_data", "exp_status"),
    [
        (
            "Swimming",
            SwimmingMetaData(
                segments=[
                    LapData(
                        count=10,
                        style=SwimStyle.FREESTYLE,
                        duration=timedelta(minutes=20),
                        lap_lenths=50,
                    ),
                    LapData(count=10),
                    LapData(count=10, style=SwimStyle.FREESTYLE),
                ]
            ),
            200,
        ),
        (
            "Swimming",
            {"some": "Data"},
            400,
        ),
    ],
)
def test_meta_data_validation(
    client: TestClient,
    db: Session,
    user1_token: str,
    activity_type_name: str,
    meta_data: BaseModel | dict,
    exp_status: int,
) -> None:
    activity_type = db.exec(
        select(ActivityType).where(ActivityType.name == activity_type_name)
    ).first()
    assert activity_type is not None
    assert activity_type.id is not None
    activity_create = ActivityCreate(
        start=datetime(2024, 1, 1, 10),
        duration=timedelta(minutes=30),
        distance=1.0,
        moving_duration=timedelta(minutes=25),
        type_id=activity_type.id,
        sub_type_id=None,
        name="Swiming activity",
        meta_data=meta_data.model_dump(mode="json")
        if isinstance(meta_data, BaseModel)
        else meta_data,
    )
    response = client.post(
        "/activity",
        json=activity_create.model_dump(exclude_unset=True, mode="json"),
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == exp_status
    if exp_status == 200:
        _create_activity = ActivityPublic.model_validate(response.json())
        assert True
