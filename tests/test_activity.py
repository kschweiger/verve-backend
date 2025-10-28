from datetime import datetime, timedelta
from importlib import resources

import pytest
from fastapi.testclient import TestClient

from verve_backend.models import (
    ActivitiesPublic,
    ActivityCreate,
    ActivityPublic,
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
        ({}, None, 1, "Fahrt am Morgen"),
        ({}, None, 3, "Aktivität am Morgen"),
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
    client: TestClient,
    user1_token: str,
) -> None:
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
    print(raw_data)
    assert len(raw_data["data"]) > 0
