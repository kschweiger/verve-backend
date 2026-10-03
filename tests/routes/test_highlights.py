from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import (
    Activity,
    ActivityHighlight,
    ActivityHighlightPublic,
    DictResponse,
    HighlightMetric,
    HighlightTimeScope,
    ListResponse,
    UserSettings,
)
from verve_backend.tasks import process_activity_highlights


def valid_activity_id(db: Session, user_id) -> UUID:
    activity = Activity(
        timezone="Europe/Berlin",
        user_id=user_id,
        start=datetime.now().astimezone(),
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


def test_yearly_highlight_uses_user_local_year(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    settings = db.get(UserSettings, temp_user_id)
    assert settings is not None
    settings.timezone = "America/Los_Angeles"  # type: ignore
    db.add(settings)

    activity = Activity(
        timezone="Europe/Berlin",
        user_id=temp_user_id,
        start=datetime(2025, 1, 1, 7, 30, tzinfo=UTC),
        duration=timedelta(minutes=30),
        distance=1.0,
        type_id=1,
        sub_type_id=None,
        name="Local 2024 activity",
    )
    db.add(activity)
    db.commit()

    process_activity_highlights(activity_id=activity.id, user_id=temp_user_id)

    headers = {"Authorization": f"Bearer {temp_user_token}"}
    for path in (
        "/highlights/",
        "/highlights/metric/distance",
        f"/highlights/activity/{activity.id}",
    ):
        response = client.get(path, headers=headers, params={"year": 2024})
        assert response.status_code == 200
        data = response.json()["data"]
        highlights = (
            data[HighlightMetric.DISTANCE.value] if isinstance(data, dict) else data
        )
        distance_highlights = [
            highlight
            for highlight in highlights
            if highlight["metric"] == HighlightMetric.DISTANCE.value
        ]
        assert len(distance_highlights) == 1
        assert distance_highlights[0]["activity_id"] == str(activity.id)
        assert distance_highlights[0]["year"] == 2024


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


@pytest.mark.parametrize("year", [2025, None])
def test_get_highlights(
    client: TestClient,
    user1_token: str,
    year: int | None,
) -> None:
    response = client.get(
        "/highlights/",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"year": year} if year else {},
    )
    assert response.status_code == 200
    results = DictResponse[
        HighlightMetric, list[ActivityHighlightPublic]
    ].model_validate(response.json())
    assert len(results.data) > 0
    for key, value in results.data.items():
        HighlightMetric(key)
        assert isinstance(value, list)
        assert len(value) > 0
        assert value[0].scope == (
            HighlightTimeScope.YEARLY if year else HighlightTimeScope.LIFETIME
        )


@pytest.mark.parametrize("year", [2025, None])
@pytest.mark.parametrize(
    "metric",
    [HighlightMetric.DISTANCE, HighlightMetric.DURATION, HighlightMetric.AVG_POWER5MIN],
)
def test_get_highlights_single_metric(
    client: TestClient,
    user1_token: str,
    year: int | None,
    metric: HighlightMetric,
) -> None:
    response = client.get(
        f"/highlights/metric/{metric.value}",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"year": year} if year else {},
    )
    assert response.status_code == 200
    results = ListResponse[ActivityHighlightPublic].model_validate(response.json())
    assert len(results.data) > 0
    assert all(
        hl.scope == (HighlightTimeScope.YEARLY if year else HighlightTimeScope.LIFETIME)
        for hl in results.data
    )


@pytest.mark.parametrize(("exp_data", "type_id"), [(True, 1), (False, 999)])
def test_get_highlights_metric_with_type_id(
    client: TestClient, user1_token: str, exp_data: bool, type_id: int
) -> None:
    response = client.get(
        f"/highlights/metric/{HighlightMetric.DISTANCE.value}",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"type_id": type_id},
    )
    assert response.status_code == 200
    results = ListResponse[ActivityHighlightPublic].model_validate(response.json())
    if exp_data:
        assert len(results.data) > 0
        assert all(h.type_id == type_id for h in results.data)
    else:
        assert len(results.data) == 0

    response = client.get(
        "/highlights/",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"type_id": type_id},
    )
    assert response.status_code == 200
    results = DictResponse[
        HighlightMetric, list[ActivityHighlightPublic]
    ].model_validate(response.json())

    for hl in results.data.values():
        if exp_data:
            assert len(hl) > 0
            assert all(h.type_id == type_id for h in hl)
        else:
            assert len(hl) == 0
