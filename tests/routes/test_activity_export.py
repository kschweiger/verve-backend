from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.models import Activity, TrackPoint


@pytest.fixture
def export_activity(db: Session, temp_user_id: UUID) -> Activity:
    activity = Activity(
        user_id=temp_user_id,
        name="Export test",
        type_id=1,
        sub_type_id=None,
        distance=1,
        timezone="UTC",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        duration=timedelta(seconds=60),
    )
    db.add(activity)
    db.commit()
    for index in range(2):
        db.add(
            TrackPoint(
                id=index,
                activity_id=activity.id,
                user_id=temp_user_id,
                segment_id=0,
                geography=f"SRID=4326;POINT(11 {48 + index * 0.001})",
                elevation=500,
                time=activity.start + timedelta(seconds=index * 60),
            )
        )
    db.commit()
    return activity


@pytest.mark.parametrize("output_format", [None, "geojson", "gpx"])
def test_download_activity(
    client: TestClient,
    temp_user_token: str,
    export_activity: Activity,
    output_format: str | None,
) -> None:
    response = client.get(
        f"/activity/{export_activity.id}/export",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={} if output_format is None else {"output_format": output_format},
    )
    extension = "gpx" if output_format == "gpx" else "json"
    assert response.status_code == 200
    assert response.content
    assert response.headers["content-type"] == (
        "application/gpx+xml" if extension == "gpx" else "application/geo+json"
    )
    assert response.headers["content-disposition"] == (
        f'attachment; filename="activity-{export_activity.id}.{extension}"'
    )


@pytest.mark.parametrize("output_format", ["geojson", "gpx"])
@pytest.mark.parametrize(
    "condition",
    ["empty", "nonspatial", "missing-elevation", "missing-time", "single-point"],
)
def test_unsupported_export_data(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    export_activity: Activity,
    output_format: str,
    condition: str,
) -> None:
    points = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == export_activity.id)
    ).all()
    if condition == "empty":
        for point in points:
            db.delete(point)
    elif condition == "nonspatial":
        points[0].geography = None
    elif condition == "missing-elevation":
        points[0].elevation = None
    elif condition == "missing-time":
        points[0].time = None
    else:
        db.delete(points[0])
    db.commit()
    response = client.get(
        f"/activity/{export_activity.id}/export",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"output_format": output_format},
    )
    expected = (
        200
        if output_format == "gpx" and condition not in {"empty", "nonspatial"}
        else 422
    )
    assert response.status_code == expected


def test_export_access_and_format_validation(
    client: TestClient,
    temp_user_token: str,
    user1_token: str,
    export_activity: Activity,
) -> None:
    path = f"/activity/{export_activity.id}/export"
    assert client.get(path).status_code == 401
    assert (
        client.get(path, headers={"Authorization": f"Bearer {user1_token}"}).status_code
        == 404
    )
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    assert client.get(f"/activity/{uuid4()}/export", headers=headers).status_code == 404
    assert (
        client.get(path, headers=headers, params={"output_format": "fit"}).status_code
        == 422
    )
