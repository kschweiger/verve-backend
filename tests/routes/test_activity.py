import io
import json
from datetime import datetime, timedelta
from importlib import resources
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from pytest_mock import MockerFixture
from sqlmodel import Session, select

from verve_backend import crud
from verve_backend.core.meta_data import LapData, SwimmingMetaData, SwimStyle
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ActivityHighlight,
    ActivityPublic,
    ActivityType,
    EquipmentSet,
    Image,
    LocationCreate,
    RawTrackData,
    TrackPoint,
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
                        lap_lengths=50,
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


def test_create_with_default_equipment_set(
    mocker: MockerFixture,
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    set_id = crud.get_default_equipment_set(
        session=db,
        user_id=user1_id,
        # NOTE: Created in conftest
        activity_type_id=1,
        activity_sub_type_id=1,
    ).unwrap()
    assert set_id is not None
    e_set = db.get(EquipmentSet, set_id)
    assert e_set is not None
    assert len(e_set.items) > 0

    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user1_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
        params={"add_default_equipment": True, "type_id": 1, "sub_type_id": 1},
    )

    assert response.status_code == 200
    _activity = ActivityPublic.model_validate(response.json())
    activity = db.get(Activity, _activity.id)
    assert activity is not None
    assert all(e in activity.equipment for e in e_set.items)


def test_create_default_equipment_set_enabled_but_none_set(
    mocker: MockerFixture,
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    set_id = crud.get_default_equipment_set(
        session=db,
        user_id=user1_id,
        activity_type_id=1,
        activity_sub_type_id=2,
    ).unwrap()
    assert set_id is None

    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user1_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
        params={"add_default_equipment": True, "type_id": 1, "sub_type_id": 2},
    )

    assert response.status_code == 200
    _activity = ActivityPublic.model_validate(response.json())
    activity = db.get(Activity, _activity.id)
    assert activity is not None
    assert len(activity.equipment) == 0


def test_create_activity_with_default_equipment_set(
    client: TestClient,
    db: Session,
    user1_token: str,
    user1_id: UUID,
) -> None:
    set_id = crud.get_default_equipment_set(
        session=db,
        user_id=user1_id,
        # NOTE: Created in conftest
        activity_type_id=1,
        activity_sub_type_id=1,
    ).unwrap()
    assert set_id is not None
    e_set = db.get(EquipmentSet, set_id)
    assert e_set is not None
    assert len(e_set.items) > 0

    activity_create = ActivityCreate(
        start=datetime(2024, 3, 1, 10),
        duration=timedelta(minutes=30),
        distance=1.0,
        moving_duration=timedelta(minutes=25),
        type_id=1,
        sub_type_id=1,
        name="Some Name",
    )
    response = client.post(
        "/activity",
        json=activity_create.model_dump(exclude_unset=True, mode="json"),
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"add_default_equipment": True},
    )
    assert response.status_code == 200
    _activity = ActivityPublic.model_validate(response.json())
    activity = db.get(Activity, _activity.id)
    assert activity is not None
    assert all(e in activity.equipment for e in e_set.items)


def test_delete_activity_without_track_and_images(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    temp_user_id: UUID,
) -> None:
    """Test deleting an activity without track or images."""
    # Create activity
    activity = Activity(
        start=datetime(2024, 1, 1, 10),
        duration=timedelta(minutes=30),
        distance=1.0,
        type_id=1,
        sub_type_id=1,
        name="Test Activity",
        user_id=temp_user_id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    activity_id = activity.id
    # Delete activity
    response = client.delete(
        f"/activity/{activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 204

    db.expire_all()
    # Verify activity is deleted
    deleted_activity = db.get(Activity, activity_id)
    assert deleted_activity is None


def test_delete_activity_with_track_no_images(
    mocker: MockerFixture,
    client: TestClient,
    db: Session,
    temp_user_token: str,
) -> None:
    """Test deleting an activity with track but no images."""
    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")

    # Upload activity with track
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    # Verify track data exists
    track_points = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == activity_id)
    ).all()
    assert len(track_points) > 0

    raw_track_data = db.exec(
        select(RawTrackData).where(RawTrackData.activity_id == activity_id)
    ).first()
    assert raw_track_data is not None

    # Delete activity
    response = client.delete(
        f"/activity/{activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 204

    db.expire_all()
    # Verify activity is deleted
    deleted_activity = db.get(Activity, activity_id)
    assert deleted_activity is None

    # Verify track points are deleted
    remaining_track_points = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == activity_id)
    ).all()
    assert len(remaining_track_points) == 0

    # Verify raw track data is deleted
    remaining_raw_track_data = db.exec(
        select(RawTrackData).where(RawTrackData.activity_id == activity_id)
    ).first()
    assert remaining_raw_track_data is None


def test_delete_activity_with_track_and_images(
    mocker: MockerFixture,
    client: TestClient,
    db: Session,
    temp_user_token: str,
) -> None:
    """Test deleting an activity with both track and images."""
    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")

    # Upload activity with track
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    # Add image to activity
    png_data = bytes.fromhex(
        "89504E470D0A1A0A0000000D494844520000000100000001080200000090"
        "77530E0000000C49444154089963000000020001E221BC330000000049454E44AE426082"
    )
    response = client.put(
        f"/media/image/activity/{activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("test.png", io.BytesIO(png_data), "image/png")},
    )

    assert response.status_code == 200
    image_id = response.json()["id"]

    # Delete activity
    response = client.delete(
        f"/activity/{activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 204

    db.expire_all()
    # Verify activity is deleted
    deleted_activity = db.get(Activity, activity_id)
    assert deleted_activity is None

    # Verify image is deleted
    deleted_image = db.get(Image, image_id)
    assert deleted_image is None


def test_auto_activity_json_with_geo_e2e_with_eager_celery(
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    with (
        resources.files("tests.resources")
        .joinpath("processed_Walk.json")
        .open("rb") as f
    ):
        json_content = f.read()

    _data = json.loads(json_content)
    _data["properties"] = None
    json_content = json.dumps(_data).encode("utf-8")

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("Walk.json", json_content, "application/octet-stream")},
        params={"type_id": 2, "sub_type_id": 7},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is not None
    assert distance_highlight.value > 0


def test_auto_activity_json_without_geo_e2e_with_eager_celery(
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    with (
        resources.files("tests.resources")
        .joinpath("processed_Weight_Training.json")
        .open("rb") as f
    ):
        json_content = f.read()

    _data = json.loads(json_content)
    _data["properties"] = None
    json_content = json.dumps(_data).encode("utf-8")

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("Walk.json", json_content, "application/octet-stream")},
        params={"type_id": 5, "sub_type_id": 19},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    # Example of a more specific check
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is None

    duration_highlight = next((h for h in highlights if h.metric == "duration"), None)
    assert duration_highlight is not None
    assert duration_highlight.value > 0


def test_auto_activity_verve_file_with_geo_e2e_with_eager_celery(
    mocker: MockerFixture,
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    from verve_backend.api.routes import activity

    spy = mocker.spy(activity, "_import_verve_file")
    with (
        resources.files("tests.resources")
        .joinpath("processed_Walk.json")
        .open("rb") as f
    ):
        json_content = f.read()

    response = client.post(
        "/activity/auto/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("Walk.json", json_content, "application/octet-stream")},
        params={"type_id": 2, "sub_type_id": 7},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    assert spy.call_count == 1
    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    # Example of a more specific check
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is not None
    assert distance_highlight.value > 0


def test_import_activity_verve_file_with_geo_e2e_with_eager_celery(
    mocker: MockerFixture,
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    from verve_backend.api.routes import activity

    spy = mocker.spy(activity, "_import_verve_file")
    with (
        resources.files("tests.resources")
        .joinpath("processed_Walk.json")
        .open("rb") as f
    ):
        json_content = f.read()

    response = client.post(
        "/activity/import/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("Walk.json", json_content, "application/octet-stream")},
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    assert spy.call_count == 1

    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    # Example of a more specific check
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is not None
    assert distance_highlight.value > 0


def test_import_activity_verve_file_without_geo_e2e_with_eager_celery(
    mocker: MockerFixture,
    client: TestClient,
    user2_token: str,
    db: Session,
    celery_eager,
) -> None:
    from verve_backend.api.routes import activity

    spy = mocker.spy(activity, "_import_verve_file")
    with (
        resources.files("tests.resources")
        .joinpath("processed_Weight_Training.json")
        .open("rb") as f
    ):
        json_content = f.read()

    response = client.post(
        "/activity/import/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={
            "file": ("Weight_Training.json", json_content, "application/octet-stream")
        },
    )
    assert response.status_code == 200
    activity_id = response.json()["id"]

    assert spy.call_count == 1

    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.activity_id == activity_id)
    ).all()

    assert len(highlights) > 0
    # Example of a more specific check
    distance_highlight = next((h for h in highlights if h.metric == "distance"), None)
    assert distance_highlight is None

    duration_highlight = next((h for h in highlights if h.metric == "duration"), None)
    assert duration_highlight is not None
    assert duration_highlight.value > 0


def test_import_invalid_json_file(
    mocker: MockerFixture,
    client: TestClient,
    user2_token: str,
) -> None:
    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")
    with (
        resources.files("tests.resources")
        .joinpath("processed_Walk.json")
        .open("rb") as f
    ):
        json_content = f.read()
    _data = json.loads(json_content)
    _data["properties"] = None
    json_content = json.dumps(_data).encode("utf-8")
    response = client.post(
        "/activity/import/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("Walk.json", json_content, "application/octet-stream")},
    )
    assert response.status_code == 422


def test_import_invalid_other_file(
    mocker: MockerFixture,
    client: TestClient,
    user2_token: str,
) -> None:
    mocker.patch("verve_backend.api.routes.activity.process_activity_highlights.delay")
    with resources.files("tests.resources").joinpath("MyWhoosh_1.fit").open("rb") as f:
        fit_content = f.read()
    response = client.post(
        "/activity/import/",
        headers={"Authorization": f"Bearer {user2_token}"},
        files={"file": ("MyWhoosh_1.fit", fit_content, "application/octet-stream")},
    )
    assert response.status_code == 422


def test_add_and_rm_location_to_activity(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    temp_user_id: UUID,
) -> None:
    """Test deleting an activity without track or images."""
    # Create activity
    activity = Activity(
        start=datetime(2024, 1, 1, 10),
        duration=timedelta(minutes=30),
        distance=1.0,
        type_id=1,
        sub_type_id=1,
        name="Test Activity",
        user_id=temp_user_id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    location = crud.create_location(
        session=db,
        user_id=temp_user_id,
        data=LocationCreate(
            name="Test Location",
            description="A location for testing",
            latitude=1,
            longitude=1,
            type_id=1,
            sub_type_id=1,
        ),
    ).unwrap()

    assert len(activity.locations) == 0

    activity_id = activity.id
    # Delete activity
    response = client.patch(
        f"/activity/{activity_id}/add_location",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"location_id": str(location.id)},
    )

    assert response.status_code == 200

    db.expire_all()  # Clear all cached objects
    _activity = db.get(Activity, activity_id)
    assert _activity is not None
    assert len(_activity.locations) == 1
    assert _activity.locations[0].id == location.id

    response = client.delete(
        f"/activity/{activity_id}/locations/{location.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    db.expire_all()  # Clear all cached objects
    _activity = db.get(Activity, activity_id)
    assert _activity is not None
    assert len(_activity.locations) == 0
