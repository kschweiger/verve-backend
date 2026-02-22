import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.crud import get_by_name
from verve_backend.models import (
    ActivitiesPublic,
    ActivityCreate,
    ActivityPublic,
    ActivitySubType,
    ActivityType,
    DictResponse,
    ListResponse,
    LocationCreate,
    LocationPublic,
    LocationSubType,
    LocationType,
)


def test_add_loacation(
    client: TestClient,
    temp_user_token: str,
) -> None:
    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
        ).model_dump(),
    )

    assert response.status_code == 200
    LocationPublic.model_validate(response.json())


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91.0, 0.0),  # Invalid latitude > 90
        (-91.0, 0.0),  # Invalid latitude < -90
        (0.0, 181.0),  # Invalid longitude > 180
        (0.0, -181.0),  # Invalid longitude < -180
    ],
)
def test_create_validation(
    client: TestClient,
    temp_user_token: str,
    latitude: float,
    longitude: float,
) -> None:
    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=dict(
            name="Test Location",
            description="A location for testing",
            latitude=latitude,
            longitude=longitude,
        ),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("params", "exp_len"),
    [
        # ------------- Select with complete window
        (
            {
                "latitude_lower_bound": 0.5,
                "latitude_upper_bound": 1.5,
                "longitude_lower_bound": 0.5,
                "longitude_upper_bound": 1.5,
            },
            2,
        ),
        # ------------- Select with left bound
        (
            {
                "longitude_lower_bound": -2,
            },
            3,
        ),
        # ------------- Select with type_id only
        (
            {"type_id": 1},
            2,
        ),
        # ------------- Select with type_id and sub_type_id
        (
            {"type_id": 1, "sub_type_id": 2},
            1,
        ),
        # ------------- Select with type_id and sub_type_id
        (
            {"type_id": 2, "sub_type_id": 8},
            2,
        ),
        # ------------- Select manual mapped with type_id and sub_type_id
        (
            {"type_id": 5, "sub_type_id": 22},
            1,
        ),
    ],
)
def test_get_locations(
    client: TestClient,
    temp_user_token: str,
    params: dict,
    exp_len: int,
) -> None:
    for i, (lat, long, _type_id, _sub_type_id) in enumerate(
        [(1, 1, 1, 1), (1.2, 1.2, 1, 2), (3, 3, 2, 8), (-3, -3, 2, 8), (-6, -6, 5, 22)]
    ):
        response = client.put(
            "/location/",
            headers={"Authorization": f"Bearer {temp_user_token}"},
            json=LocationCreate(
                name=f"Test Location {i}",
                latitude=lat,
                longitude=long,
                type_id=_type_id,
                sub_type_id=_sub_type_id,
            ).model_dump(),
        )

        assert response.status_code == 200
        loc = LocationPublic.model_validate(response.json())
    response = client.post(
        "/activity",
        json=ActivityCreate(
            start=datetime(2024, 1, 1, 10),
            duration=timedelta(minutes=30),
            distance=1.0,
            moving_duration=timedelta(minutes=25),
            type_id=1,
            sub_type_id=None,
            name="Some Name",
        ).model_dump(exclude_unset=True, mode="json"),
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    act = ActivityPublic.model_validate(response.json())
    client.patch(
        f"/activity/{act.id}/add_location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"location_id": str(loc.id)},
    )

    assert response.status_code == 200
    response = client.get(
        "/location/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200
    data = ListResponse[LocationPublic].model_validate(response.json())
    assert len(data.data) == 5

    # ------------- Select with complete window
    response = client.get(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params=params,
    )

    assert response.status_code == 200
    data = ListResponse[LocationPublic].model_validate(response.json())
    assert len(data.data) == exp_len


def test_delete_location(
    client: TestClient,
    temp_user_token: str,
) -> None:
    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
        ).model_dump(),
    )

    assert response.status_code == 200
    location = LocationPublic.model_validate(response.json())

    response = client.delete(
        f"/location/{location.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200

    response = client.get(
        f"/location/{location.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 404


def test_update_location(
    client: TestClient,
    temp_user_token: str,
) -> None:
    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
        ).model_dump(),
    )

    assert response.status_code == 200
    location = LocationPublic.model_validate(response.json())

    for attr, value in [("name", "New name"), ("description", "New description")]:
        response = client.post(
            f"/location/{location.id}",
            headers={"Authorization": f"Bearer {temp_user_token}"},
            params={"attribute": attr, "value": value},
        )

        assert response.status_code == 200
        updated_location = LocationPublic.model_validate(response.json())
        assert getattr(updated_location, attr) == value

    response = client.get(
        f"/location/{location.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    location = LocationPublic.model_validate(response.json())

    assert location.name == "New name"
    assert location.description == "New description"


def test_activities_with_location(
    client: TestClient,
    user2_token: str,
) -> None:
    response = client.get(
        "/location/",
        headers={"Authorization": f"Bearer {user2_token}"},
    )

    assert response.status_code == 200
    all_locatons = ListResponse[LocationPublic].model_validate(response.json())
    # NOTE: We expect the Mont Vontoux location to be present from the dummy data
    assert len(all_locatons.data) == 2

    respones = client.get(
        f"/location/{all_locatons.data[0].id}/activities",
        headers={"Authorization": f"Bearer {user2_token}"},
    )

    assert respones.status_code == 200

    activities = ActivitiesPublic.model_validate(respones.json())

    assert activities.count == 1


def test_get_all_activities(
    client: TestClient,
    user2_token: str,
) -> None:
    response = client.get(
        "/location/activities", headers={"Authorization": f"Bearer {user2_token}"}
    )

    assert response.status_code == 200

    data = DictResponse[uuid.UUID, set[uuid.UUID]].model_validate(response.json())

    assert len(data.data) == 2
    assert len(data.data[next(iter(data.data))]) == 1


def test_get_all_activities_location_ids(
    db: Session,
    client: TestClient,
    user2_token: str,
) -> None:
    response = client.get(
        "/location/activities",
        headers={"Authorization": f"Bearer {user2_token}"},
        params={
            "location_type_id": get_by_name(db, LocationType, "Facilities").unwrap().id,
            "location_sub_type_id": get_by_name(db, LocationSubType, "Gym").unwrap().id,
        },
    )

    assert response.status_code == 200

    data = DictResponse[uuid.UUID, set[uuid.UUID]].model_validate(response.json())

    assert len(data.data) == 1
    assert len(data.data[next(iter(data.data))]) == 1


def test_get_all_activities_activity_ids(
    db: Session,
    client: TestClient,
    user2_token: str,
) -> None:
    response = client.get(
        "/location/activities",
        headers={"Authorization": f"Bearer {user2_token}"},
        params={
            "activity_type_id": get_by_name(db, ActivityType, "Strength Training")
            .unwrap()
            .id,
            "activity_sub_type_id": get_by_name(db, ActivitySubType, "Weight Training")
            .unwrap()
            .id,
        },
    )

    assert response.status_code == 200

    data = DictResponse[uuid.UUID, set[uuid.UUID]].model_validate(response.json())

    assert len(data.data) == 1
    assert len(data.data[next(iter(data.data))]) == 1


def test_modify_location_type(
    db: Session,
    client: TestClient,
    temp_user_token: str,
) -> None:
    sub_type = db.exec(
        select(LocationSubType).where(LocationSubType.name == "Climbing Gym")
    ).first()

    assert sub_type is not None

    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
            type_id=1,
            sub_type_id=1,
        ).model_dump(),
    )

    assert response.status_code == 200

    location = LocationPublic.model_validate(response.json())
    assert location.type_id == 1
    assert location.sub_type_id == 1

    response = client.patch(
        f"/location/{location.id}/replace_type",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "type_id": sub_type.type_id,
            "sub_type_id": sub_type.id,
        },
    )

    assert response.status_code == 200

    LocationPublic.model_validate(response.json())

    response = client.get(
        f"/location/{location.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    location = LocationPublic.model_validate(response.json())

    assert location.type_id == sub_type.type_id
    assert location.sub_type_id == sub_type.id


def test_modify_location_type_invalid_combination(
    db: Session,
    client: TestClient,
    temp_user_token: str,
) -> None:
    sub_type = db.exec(
        select(LocationSubType).where(LocationSubType.name == "Climbing Gym")
    ).first()

    assert sub_type is not None
    assert sub_type.type_id > 1

    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
            type_id=1,
            sub_type_id=1,
        ).model_dump(),
    )

    assert response.status_code == 200

    location = LocationPublic.model_validate(response.json())

    response = client.patch(
        f"/location/{location.id}/replace_type",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "type_id": 1,
            "sub_type_id": sub_type.id,
        },
    )

    assert response.status_code == 400


def test_modify_location_type_invalid_sub_type(
    client: TestClient,
    temp_user_token: str,
) -> None:
    response = client.put(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
            type_id=1,
            sub_type_id=1,
        ).model_dump(),
    )

    assert response.status_code == 200

    location = LocationPublic.model_validate(response.json())

    response = client.patch(
        f"/location/{location.id}/replace_type",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "type_id": 1,
            "sub_type_id": 22222,
        },
    )

    assert response.status_code == 404
