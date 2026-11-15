from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
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


@pytest.mark.parametrize(
    "condition",
    [
        "valid",
        "empty",
        "nonspatial",
        "missing-elevation",
        "missing-time",
        "single-point",
    ],
)
def test_activity_exportability(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    export_activity: Activity,
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
    elif condition == "single-point":
        db.delete(points[0])
    db.commit()

    response = client.get(
        f"/activity/{export_activity.id}/is_exportable",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"is_exportable": condition == "valid"}


@pytest.mark.parametrize("second_segment_size", [1, 2])
def test_exportability_requires_each_segment_to_be_valid(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    export_activity: Activity,
    second_segment_size: int,
) -> None:
    for index in range(second_segment_size):
        db.add(
            TrackPoint(
                id=index + 2,
                activity_id=export_activity.id,
                user_id=export_activity.user_id,
                segment_id=1,
                geography="SRID=4326;POINT(11 48)",
                elevation=0,
                time=export_activity.start + timedelta(seconds=index),
            )
        )
    db.commit()
    response = client.get(
        f"/activity/{export_activity.id}/is_exportable",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"is_exportable": second_segment_size == 2}


def test_exportability_access_and_id_validation(
    client: TestClient,
    temp_user_token: str,
    user1_token: str,
    export_activity: Activity,
) -> None:
    path = f"/activity/{export_activity.id}/is_exportable"
    assert client.get(path).status_code == 401
    assert (
        client.get(path, headers={"Authorization": f"Bearer {user1_token}"}).status_code
        == 404
    )
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.get(f"/activity/{uuid4()}/is_exportable", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Activity not found"}
    assert (
        client.get("/activity/not-a-uuid/is_exportable", headers=headers).status_code
        == 422
    )


def test_exportability_does_not_load_or_export_track(
    export_activity: Activity,
    mocker: MockerFixture,
) -> None:
    from verve_backend.api.deps import _create_rls_session
    from verve_backend.api.routes import activity

    mocker.patch.object(
        activity, "load_activity_track", side_effect=AssertionError("Track loaded")
    )
    mocker.patch.object(
        activity, "_cast", side_effect=AssertionError("Export attempted")
    )
    with _create_rls_session(export_activity.user_id) as session:
        get_spy = mocker.spy(session, "get")
        exec_spy = mocker.spy(session, "exec")
        response = activity.is_activity_exportable(
            (str(export_activity.user_id), session), export_activity.id
        )
        assert response.is_exportable is True
        assert get_spy.call_count == 1
        assert exec_spy.call_count == 1
