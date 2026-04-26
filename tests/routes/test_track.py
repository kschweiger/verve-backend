import uuid
from datetime import datetime, timedelta
from importlib import resources

import pytest
from fastapi.testclient import TestClient
from geo_track_analyzer import GPXFileTrack
from sqlmodel import Session, col, select

from verve_backend import crud
from verve_backend.api.routes.track import SegmentSetPublic, SegmentStatisticsResponse
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ListResponse,
    SegmentCut,
    SegmentSet,
    User,
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
        f"/track/segments/set/{_set.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200

    SegmentStatisticsResponse.model_validate(response.json())


def test_get_segment_stats_invalid_segment(
    client: TestClient, user1_token: str
) -> None:
    response = client.get(
        "/track/segments/set/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 404


def test_get_segment_sets(
    db: Session,
    client: TestClient,
    user1_id: uuid.UUID,
    user1_token: str,
) -> None:
    _sets = db.exec(select(SegmentSet).where(SegmentSet.user_id == user1_id)).all()
    assert len(_sets) > 0
    activity_id = _sets[0].activity_id

    response = client.get(
        f"/track/segments/sets/{activity_id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200

    res_data = ListResponse[uuid.UUID].model_validate(response.json())

    assert len(res_data.data) > 0
    assert len(res_data.data) == len(_sets)


def _add_activity(
    db: Session,
    user: User,
) -> Activity:
    activity = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=1, day=1, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=None,
            type_id=1,
            sub_type_id=1,
            name=None,
        ),
        user=user,  # type: ignore
    ).unwrap()

    resource_files = resources.files("tests.resources")
    track = GPXFileTrack(resource_files / "two_segments_100_points.gpx")  # type: ignore
    crud.insert_track(
        session=db,
        track=track,
        activity_id=activity.id,
        user_id=user.id,
        batch_size=500,
    )

    return activity


def test_add_segment(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)
    _sets = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).all()
    assert len(_sets) == 1

    response = client.post(
        "/track/segments/set",
        json=dict(name="Some name", activity_id=str(activity.id), cuts=[20, 60]),
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    new_set = SegmentSetPublic.model_validate(response.json())

    db.reset()
    _sets = db.exec(select(SegmentSet).where(SegmentSet.user_id == temp_user_id)).all()
    assert len(_sets) == 2

    segment_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == new_set.id)
    ).all()

    assert len(segment_cuts) == 2


def test_update_segment_no_update_data(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set
    response = client.patch(
        f"/track/segments/set/{_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=dict(),
    )

    assert response.status_code == 400


def test_update_segment_name(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    response = client.patch(
        f"/track/segments/set/{_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=dict(name="New name"),
    )

    assert response.status_code == 200
    db.reset()
    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    assert _set.name == "New name"


def test_update_segment_cuts(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == _set.id)
    ).all()
    assert len(selected_cuts) > 0
    orig_cut_ids = {cut.point_id for cut in selected_cuts}
    orig_len = len(selected_cuts)

    response = client.patch(
        f"/track/segments/set/{_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=dict(cuts=[20, 40, 80]),
    )

    assert response.status_code == 200
    db.reset()
    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == _set.id)
    ).all()
    assert len(selected_cuts) == 3

    assert {cut.point_id for cut in selected_cuts} != orig_cut_ids
    assert len(selected_cuts) != orig_len


@pytest.mark.parametrize("payload", [dict(cuts=[200])])
def test_update_segment_cuts_error_states(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
    payload: dict,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == _set.id)
    ).all()
    assert len(selected_cuts) > 0
    orig_len = len(selected_cuts)

    response = client.patch(
        f"/track/segments/set/{_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=payload,
    )

    assert response.status_code == 400

    db.reset()

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == _set.id)
    ).all()
    assert len(selected_cuts) == orig_len


def test_delete_segment_set(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: uuid.UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity = _add_activity(db, user)

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.activity_id == activity.id)
    ).first()
    assert _set

    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == _set.id)
    ).all()
    assert len(selected_cuts) > 0

    set_id = _set.id
    response = client.delete(
        f"/track/segments/set/{set_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    db.reset()

    _set = db.exec(
        select(SegmentSet)
        .where(SegmentSet.user_id == temp_user_id)
        .where(SegmentSet.id == set_id)
    ).first()
    assert _set is None

    selected_cuts = db.exec(
        select(SegmentCut).where(col(SegmentCut.set_id) == set_id)
    ).all()
    assert len(selected_cuts) == 0
