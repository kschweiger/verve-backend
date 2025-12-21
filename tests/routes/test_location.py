import pytest
from fastapi.testclient import TestClient

from verve_backend.models import ListResponse, LocationCreate, LocationPublic


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


def test_get_locations(
    client: TestClient,
    temp_user_token: str,
) -> None:
    for i, (lat, long) in enumerate([(1, 1), (1.2, 1.2), (3, 3), (-3, -3)]):
        response = client.put(
            "/location",
            headers={"Authorization": f"Bearer {temp_user_token}"},
            json=LocationCreate(
                name=f"Test Location {i}",
                latitude=lat,
                longitude=long,
            ).model_dump(),
        )

        assert response.status_code == 200

    response = client.get(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200
    data = ListResponse[LocationPublic].model_validate(response.json())
    assert len(data.data) == 4

    # ------------- Select with complete window
    response = client.get(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "latitude_lower_bound": 0.5,
            "latitude_upper_bound": 1.5,
            "longitude_lower_bound": 0.5,
            "longitude_upper_bound": 1.5,
        },
    )

    assert response.status_code == 200
    data = ListResponse[LocationPublic].model_validate(response.json())
    assert len(data.data) == 2
    # ------------- Select with left bound
    response = client.get(
        "/location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "longitude_lower_bound": -2,
        },
    )

    assert response.status_code == 200
    data = ListResponse[LocationPublic].model_validate(response.json())
    assert len(data.data) == 3


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
