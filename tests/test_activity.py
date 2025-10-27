from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import (
    ActivitiesPublic,
    ActivityCreate,
    ActivityName,
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
    ("params", "type_id", "exp_name"),
    [
        ({}, 1, "Fahrt am Morgen"),
        ({}, 3, "Aktivität am Morgen"),
        ({"locale": "en"}, 1, "Morning Ride"),
        ({"locale": "de", "name": "Schöne Ausfahrt"}, 1, "Schöne Ausfahrt"),
    ],
)
def test_create_activity_wo_name(
    client: TestClient,
    user1_token: str,
    db: Session,
    params: dict[str, str],
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
    )
    response = client.post(
        "/activity",
        json=activity_create.model_dump(exclude_unset=True, mode="json"),
        headers={"Authorization": f"Bearer {user1_token}"},
        params=params,
    )

    create_activity = ActivityPublic.model_validate(response.json())
    assert response.status_code == 200

    name = db.get(ActivityName, create_activity.id)
    assert name is not None
    assert name.name == exp_name
