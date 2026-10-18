"""Swimming metadata persistence through the activity API."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.models import Activity, ActivityType


@pytest.fixture
def swimming_activity(client: TestClient, db: Session, temp_user_token: str) -> UUID:
    swimming = db.exec(
        select(ActivityType).where(ActivityType.name == "Swimming")
    ).one()
    response = client.post(
        "/activity/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"timezone_name": "Europe/Berlin"},
        json={
            "start": "2025-01-01T00:00:00Z",
            "duration": "PT10M",
            "name": "Swimming metadata",
            "type_id": swimming.id,
            "sub_type_id": None,
            "distance": 0.2,
            "meta_data": {
                "target": "SwimmingMetaData",
                "pool_length_meters": 22.86,
                "lap_count": 8,
                "total_stroke_count": 0,
                "custom": "keep",
            },
        },
    )
    assert response.status_code == 200, response.text
    activity_id = UUID(response.json()["id"])
    db.expire_all()
    activity = db.get(Activity, activity_id)
    assert activity is not None
    assert activity.meta_data["pool_length_meters"] == pytest.approx(22.86)
    assert activity.meta_data["lap_count"] == 8
    assert activity.meta_data["total_stroke_count"] == 0
    assert activity.meta_data["custom"] == "keep"
    return activity_id


def test_patch_preserves_partial_metadata_custom_fields_and_timezone(
    client: TestClient, db: Session, temp_user_token: str, swimming_activity: UUID
) -> None:
    response = client.patch(
        f"/activity/{swimming_activity}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={
            "meta_data": {
                "target": "SwimmingMetaData",
                "custom": {"preserve": True},
                "laps": [
                    {
                        "index": 0,
                        "distance_meters": 22.86,
                        "stroke_count": 0,
                        "custom": "nested",
                        "start_time": "2025-01-01T00:30:00",
                        "end_time": "2025-01-01T01:40:00+02:00",
                    }
                ],
                "sets": [],
            }
        },
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    activity = db.get(Activity, swimming_activity)
    assert activity is not None
    metadata = activity.meta_data
    assert metadata["custom"] == {"preserve": True}
    assert metadata["sets"] == []
    assert "lap_count" not in metadata
    lap = metadata["laps"][0]
    assert lap["custom"] == "nested"
    assert lap["distance_meters"] == pytest.approx(22.86)
    assert lap["stroke_count"] == 0
    assert datetime.fromisoformat(lap["start_time"]) == datetime(
        2024, 12, 31, 23, 30, tzinfo=UTC
    )
    assert datetime.fromisoformat(lap["end_time"]) == datetime(
        2024, 12, 31, 23, 40, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param({"lap_count": 1, "laps": []}, id="count-mismatch"),
        pytest.param({"custom": "only"}, id="unknown-only"),
        pytest.param({"laps": [{"index": 1}]}, id="invalid-index"),
        pytest.param(
            {"laps": [{"index": 0, "durations": True}]}, id="boolean-duration"
        ),
        pytest.param(
            {
                "laps": [
                    {
                        "index": 0,
                        "start_time": "2025-01-01T00:30:00",
                        "end_time": "2025-01-01T00:40:00+02:00",
                    }
                ]
            },
            id="reversed-normalized-interval",
        ),
        pytest.param(
            {"sets": [{"index": 0, "lap_start_index": 0}]}, id="unavailable-reference"
        ),
    ],
)
def test_invalid_patch_leaves_activity_unchanged(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    swimming_activity: UUID,
    metadata: dict[str, Any],
) -> None:
    activity = db.get(Activity, swimming_activity)
    assert activity is not None
    original = activity.model_dump(mode="json")
    response = client.patch(
        f"/activity/{swimming_activity}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={
            "name": "Must not persist",
            "meta_data": {"target": "SwimmingMetaData", **metadata},
        },
    )
    assert response.status_code == 422, response.text
    db.expire_all()
    db.refresh(activity)
    assert activity.model_dump(mode="json") == original


def test_create_rejects_interval_reversed_after_normalization_without_writes(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    swimming = db.exec(
        select(ActivityType).where(ActivityType.name == "Swimming")
    ).one()
    existing = db.exec(
        select(Activity.id).where(Activity.user_id == temp_user_id)
    ).all()
    response = client.post(
        "/activity/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"timezone_name": "Europe/Berlin"},
        json={
            "start": "2025-01-01T00:00:00Z",
            "duration": "PT10M",
            "name": "Invalid swimming interval",
            "type_id": swimming.id,
            "sub_type_id": None,
            "distance": 0.2,
            "meta_data": {
                "target": "SwimmingMetaData",
                "laps": [
                    {
                        "index": 0,
                        "start_time": "2025-01-01T00:30:00",
                        "end_time": "2025-01-01T00:40:00+02:00",
                    }
                ],
            },
        },
    )
    assert response.status_code == 400, response.text
    assert (
        db.exec(select(Activity.id).where(Activity.user_id == temp_user_id)).all()
        == existing
    )
