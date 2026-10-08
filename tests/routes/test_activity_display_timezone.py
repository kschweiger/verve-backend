import json
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlmodel import Session, select

from verve_backend.models import Activity, RawTrackData, TrackPoint

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


@pytest.mark.parametrize("route", ["/activity/import/", "/activity/auto/"])
@pytest.mark.parametrize(
    ("override", "expected_zone", "expected_hour", "point_hour"),
    [
        pytest.param(None, "Europe/Berlin", 8, 14, id="file-zone"),
        pytest.param(
            "America/Los_Angeles", "America/Los_Angeles", 17, 23, id="request-zone"
        ),
    ],
)
def test_verve_declared_zone_wins_over_gps_and_owner_setting(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    celery_eager: None,
    mocker: MockerFixture,
    object_store: "S3Client",
    route: str,
    override: str | None,
    expected_zone: str,
    expected_hour: int,
    point_hour: int,
) -> None:
    from verve_backend.api.common import timezone
    from verve_backend.core.config import settings
    from verve_backend.schema.exporter import _cast

    lookup = mocker.spy(timezone, "infer_iana_timezone_from_coordinates")
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    assert (
        client.patch(
            "/users/me/timezone",
            headers=headers,
            params={"timezone_name": "America/Los_Angeles"},
        ).status_code
        == 200
    )
    data = json.loads(
        resources.files("tests.resources").joinpath("processed_Walk.json").read_text()
    )
    data["properties"]["timezone"] = "Europe/Berlin"
    data["properties"]["startTime"] = "2026-07-01T10:00:00"
    for feature in data["features"]:
        feature["properties"]["coordTimes"] = [
            time.removesuffix("Z") for time in feature["properties"]["coordTimes"]
        ]
    file_bytes = json.dumps(data, indent=2).encode()
    response = client.post(
        route,
        headers=headers,
        params={"timezone_name": override} if override else None,
        files={"file": ("walk.json", file_bytes, "application/json")},
    )
    assert response.status_code == 200
    activity = response.json()
    assert activity["timezone"] == expected_zone
    assert datetime.fromisoformat(activity["start"]) == datetime(
        2026, 7, 1, expected_hour, tzinfo=UTC
    )
    lookup.assert_not_called()
    exported = json.loads(_cast(db, UUID(activity["id"])).to_json())
    assert exported["properties"]["timezone"] == expected_zone
    assert datetime.fromisoformat(
        exported["properties"]["startTime"]
    ) == datetime.fromisoformat(activity["start"])
    first_point = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == UUID(activity["id"]))
    ).first()
    assert first_point is not None
    assert first_point.time == datetime(2026, 1, 13, point_hour, 22, 2, tzinfo=UTC)
    raw = db.get(RawTrackData, UUID(activity["id"]))
    assert raw is not None
    stored = object_store.get_object(Bucket=settings.BOTO3_BUCKET, Key=raw.store_path)
    with stored["Body"] as body:
        assert body.read() == file_bytes
    reimported = client.post(
        "/activity/import/",
        headers=headers,
        files={"file": ("roundtrip.json", json.dumps(exported), "application/json")},
    )
    assert reimported.status_code == 200
    assert reimported.json()["timezone"] == expected_zone
    assert reimported.json()["start"] == activity["start"]
    reimported_point = db.exec(
        select(TrackPoint).where(
            TrackPoint.activity_id == UUID(reimported.json()["id"])
        )
    ).first()
    assert reimported_point is not None
    assert reimported_point.time == first_point.time
    lookup.assert_not_called()


@pytest.mark.parametrize(
    ("query_zone", "body_zone", "expected_hour"),
    [
        pytest.param(None, None, 8, id="stored-zone"),
        pytest.param(None, "America/Los_Angeles", 17, id="patch-zone"),
        pytest.param("Europe/Berlin", "America/Los_Angeles", 8, id="query-zone"),
    ],
)
def test_swimming_patch_interprets_new_times_in_effective_activity_zone(
    client: TestClient,
    temp_user_token: str,
    query_zone: str | None,
    body_zone: str | None,
    expected_hour: int,
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    assert (
        client.patch(
            "/users/me/timezone",
            headers=headers,
            params={"timezone_name": "America/Los_Angeles"},
        ).status_code
        == 200
    )
    created = client.post(
        "/activity/",
        headers=headers,
        params={"timezone_name": "Europe/Berlin"},
        json={
            "name": "Swim",
            "start": "2026-07-01T08:00:00Z",
            "duration": 600,
            "distance": 1,
            "type_id": 4,
            "sub_type_id": None,
        },
    )
    assert created.status_code == 200
    body = {
        "meta_data": {
            "target": "SwimmingMetaData",
            "laps": [
                {
                    "index": 0,
                    "start_time": "2026-07-01T10:00:00",
                    "end_time": "2026-07-01T08:10:00Z",
                },
            ],
        }
    }
    if body_zone:
        body["timezone"] = body_zone
    response = client.patch(
        f"/activity/{created.json()['id']}",
        headers=headers,
        json=body,
        params={"timezone_name": query_zone} if query_zone else None,
    )
    assert response.status_code == 200
    activity = response.json()
    assert activity["start"] == created.json()["start"]
    lap = activity["meta_data"]["laps"][0]
    assert datetime.fromisoformat(lap["start_time"]) == datetime(
        2026, 7, 1, expected_hour, tzinfo=UTC
    )
    assert datetime.fromisoformat(lap["end_time"]) == datetime(
        2026, 7, 1, 8, 10, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("query_zone", "with_geometry", "expected_zone"),
    [
        pytest.param(None, True, "Europe/Berlin", id="gps-replaces-zone"),
        pytest.param(
            "America/New_York", True, "America/New_York", id="request-replaces-zone"
        ),
        pytest.param(None, False, "America/Los_Angeles", id="retain-stored-zone"),
    ],
)
def test_replacement_track_saves_selected_zone(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    temp_user_id: UUID,
    celery_eager: None,
    query_zone: str | None,
    with_geometry: bool,
    expected_zone: str,
) -> None:
    activity = Activity(
        timezone="America/Los_Angeles",
        user_id=temp_user_id,
        name="Replacement",
        start=datetime(2026, 7, 1, tzinfo=UTC),
        duration=timedelta(minutes=10),
        distance=1,
        type_id=1,
        sub_type_id=None,
    )
    db.add(activity)
    db.commit()
    data = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[13.405, 52.52, 10], [13.406, 52.521, 10]],
        }
        if with_geometry
        else None,
        "properties": {"coordTimes": ["2026-07-01T10:00:00Z", "2026-07-01T10:10:00Z"]},
    }
    response = client.put(
        "/track/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={
            "activity_id": str(activity.id),
            **({"timezone_name": query_zone} if query_zone else {}),
        },
        files={"file": ("track.json", json.dumps(data), "application/json")},
    )
    assert response.status_code == 201
    db.refresh(activity)
    assert activity.timezone == expected_zone
    assert activity.start == datetime(2026, 7, 1, 10, tzinfo=UTC)


def test_invalid_track_upload_does_not_create_placeholder(
    client: TestClient,
    temp_user_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    before = client.get("/activity/", headers=headers).json()["count"]
    response = client.post(
        "/activity/auto/",
        headers=headers,
        files={"file": ("unsupported.json", '{"type": "Polygon"}', "application/json")},
    )
    assert response.status_code == 422
    assert client.get("/activity/", headers=headers).json()["count"] == before


def test_invalid_verve_timezone_is_rejected_before_creation(
    client: TestClient,
    temp_user_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    before = client.get("/activity/", headers=headers).json()["count"]
    data = json.loads(
        resources.files("tests.resources").joinpath("processed_Walk.json").read_text()
    )
    data["properties"]["timezone"] = "Not/AZone"
    response = client.post(
        "/activity/import/",
        headers=headers,
        files={"file": ("walk.json", json.dumps(data), "application/json")},
    )
    assert response.status_code == 422
    assert client.get("/activity/", headers=headers).json()["count"] == before
