from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import User


def test_activity_heatmap_filters_by_user_local_year(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
    create_activity_with_gpx_track,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = create_activity_with_gpx_track(user=user, sub_type_id=None)
    activity.start = datetime(2025, 1, 1, 7, 30, tzinfo=UTC)
    db.add(activity)
    db.commit()

    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.patch(
        "/users/me/timezone",
        headers=headers,
        params={"timezone_name": "America/Los_Angeles"},
    )
    assert response.status_code == 200

    response = client.get("/heatmap/activities", headers=headers, params={"year": 2024})
    assert response.status_code == 200
    assert response.json()["points"]

    response = client.get("/heatmap/activities", headers=headers, params={"year": 2025})
    assert response.status_code == 200
    assert response.json()["points"] == []
