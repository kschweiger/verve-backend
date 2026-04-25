import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.api.routes.track import SegmentStatisticsResponse
from verve_backend.models import (
    ActivitiesPublic,
    SegmentSet,
)


def test_get_track_data(client: TestClient, user1_token: str) -> None:
    response = client.get(
        "/activity",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
    data = ActivitiesPublic.model_validate(response.json())

    assert len(data.data) > 0

    for activity in data.data:
        response = client.get(
            f"/track/{activity.id}",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
        assert response.status_code == 200


def test_get_segment_stats(
    db: Session,
    client: TestClient,
    user1_id: uuid.UUID,
    user1_token: str,
) -> None:
    _sets = db.exec(select(SegmentSet).where(SegmentSet.user_id == user1_id)).all()
    assert len(_sets) > 0
    _set = _sets[0]

    response = client.get(
        "/track/segment",
        params={
            "segment_set_id": str(_set.id),
        },
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    print(response.json())
    assert response.status_code == 200

    SegmentStatisticsResponse.model_validate(response.json())


def test_get_segment_stats_invalid_segment(
    client: TestClient, user1_token: str
) -> None:
    response = client.get(
        "/track/segment",
        params={
            "segment_set_id": "00000000-0000-0000-0000-000000000000",
        },
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 404
