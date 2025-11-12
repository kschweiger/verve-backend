from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import (
    Activity,
    ActivityHighlight,
    ActivityHighlightPublic,
    HighlightMetric,
    HighlightTimeScope,
    ListResponse,
)


def valid_activity_id(db: Session, user_id) -> UUID:
    activity = Activity(
        user_id=user_id,
        start=datetime.now(),
        distance=100,
        duration=timedelta(minutes=60),
        type_id=1,
        sub_type_id=None,
        name="Temp activity",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    return activity.id


def test_get_highlights_for_activity_nothing_in_db(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    activity_id = valid_activity_id(db, temp_user_id)

    response = client.get(
        "/highlights/activity/{activity_id}".format(activity_id=activity_id),
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    data = ListResponse[ActivityHighlightPublic].model_validate(response.json())
    assert len(data.data) == 0


def test_get_highlights_for_activity_nothing_in(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    activity_id = valid_activity_id(db, temp_user_id)
    for metric, scope, value in [
        (HighlightMetric.DISTANCE, HighlightTimeScope.YEARLY, 100.0),
        (HighlightMetric.DURATION, HighlightTimeScope.YEARLY, 60.0),
        (HighlightMetric.MAX_POWER, HighlightTimeScope.YEARLY, 222.0),
    ]:
        hl = ActivityHighlight(
            activity_id=activity_id,
            user_id=temp_user_id,
            type_id=1,
            metric=metric,
            scope=scope,
            value=value,
            year=2025 if scope == HighlightTimeScope.YEARLY else None,
            rank=1,
        )
        db.add(hl)
        db.commit()

    response = client.get(
        "/highlights/activity/{activity_id}".format(activity_id=activity_id),
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"year": 2025},
    )
    assert response.status_code == 200
    data = ListResponse[ActivityHighlightPublic].model_validate(response.json())
    assert len(data.data) == 3
    for hl in data.data:
        if hl.metric == HighlightMetric.DURATION:
            assert isinstance(hl.value, timedelta)
        elif hl.metric == HighlightMetric.MAX_POWER:
            assert isinstance(hl.value, int)
        else:
            assert isinstance(hl.value, float)
