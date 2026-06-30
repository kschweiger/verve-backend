from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend import crud
from verve_backend.api.routes.collection import CollectionListResponse
from verve_backend.models import (
    Activity,
    ActivityCollection,
    ActivityCollectionLink,
    ActivityCreate,
    User,
)


def test_activity_collection(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
    create_activity_with_gpx_track,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    activity_1 = create_activity_with_gpx_track(
        user=user,
        name="Stage 1",
        resource_name="collection_stage_1_100_points.gpx",
        type_id=1,
        sub_type_id=1,
    )
    activity_2 = create_activity_with_gpx_track(
        user=user,
        name="Stage 2",
        resource_name="collection_stage_2_100_points.gpx",
        type_id=1,
        sub_type_id=1,
    )
    response = client.post(
        "/collection",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={
            "name": "Test Collection",
            "description": "This is a really amazing collection",
            "activity_ids": [str(activity_1.id), str(activity_2.id)],
        },
    )
    assert response.status_code == 200
    _response = response.json()
    collection_id = _response.get("id")
    assert collection_id is not None

    collection = db.get(ActivityCollection, collection_id)

    assert collection is not None
    assert collection.name == "Test Collection"
    assert {a.id for a in collection.activities} == {activity_1.id, activity_2.id}


@pytest.mark.parametrize(
    ("year", "month", "exp_count"),
    [
        (None, None, 3),
        (2020, None, 0),
        (2026, None, 2),
        (2026, 6, 1),
        (2025, None, 1),
    ],
)
def test_get_collections(
    client: TestClient,
    user1_token: UUID,
    year: int | None,
    month: int | None,
    exp_count: int,
) -> None:
    _params = {"limit": 5}
    if year:
        _params["year"] = year
    if month:
        _params["month"] = month
    response = client.get(
        "/collection",
        headers={"Authorization": f"Bearer {user1_token}"},
        params=_params,
    )

    assert response.status_code == 200

    data = CollectionListResponse.model_validate(response.json())

    assert len(data.data) == exp_count


def test_update_collection(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None

    # ---------------- Create activities and colleciton ------------------
    common_data = dict(
        duration=timedelta(days=0, seconds=60 * 60 * 1),
        distance=None,
        type_id=1,
        sub_type_id=1,
    )
    activity_1 = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=4, day=1, hour=13),
            name="Collection Activity 1",
            **common_data,  # type: ignore
        ),
        user=user,  # type: ignore
    ).unwrap()
    activity_2 = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=4, day=2, hour=13),
            name="Collection Activity 2",
            **common_data,  # type: ignore
        ),
        user=user,  # type: ignore
    ).unwrap()
    activity_3 = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=4, day=3, hour=13),
            name="Collection Activity 3",
            **common_data,  # type: ignore
        ),
        user=user,  # type: ignore
    ).unwrap()

    collection = ActivityCollection(
        user_id=temp_user_id,
        name="Collection",
    )
    collection.activities.extend([activity_1])
    db.add(collection)
    db.commit()
    db.refresh(collection)
    collection_id = collection.id
    # -----------------------------------------------------------------
    response = client.patch(
        f"/collection/{collection_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={"name": "new name"},
    )

    assert response.status_code == 200

    db.expire_all()
    _collection = db.get(ActivityCollection, collection_id)
    assert _collection is not None
    assert _collection.name == "new name"

    response = client.patch(
        f"/collection/{collection_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={"description": "new description"},
    )

    assert response.status_code == 200

    db.expire_all()
    _collection = db.get(ActivityCollection, collection_id)
    assert _collection is not None
    assert _collection.description == "new description"

    db.expire_all()
    links = db.exec(
        select(ActivityCollectionLink).where(
            ActivityCollectionLink.collection_id == collection_id
        )
    ).all()
    assert len(links) == 1
    assert links[0].activity_id == activity_1.id

    response = client.patch(
        f"/collection/{collection_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={"activity_ids": [str(activity_2.id)]},
    )

    assert response.status_code == 200

    db.expire_all()
    links = db.exec(
        select(ActivityCollectionLink).where(
            ActivityCollectionLink.collection_id == collection_id
        )
    ).all()

    assert len(links) == 2
    assert links[1].activity_id == activity_2.id

    response = client.patch(
        f"/collection/{collection_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json={"activity_ids": [str(activity_3.id)], "replace_activities": True},
    )

    assert response.status_code == 200

    db.expire_all()
    links = db.exec(
        select(ActivityCollectionLink).where(
            ActivityCollectionLink.collection_id == collection_id
        )
    ).all()

    assert len(links) == 1
    assert links[0].activity_id == activity_3.id


def test_delete_collection(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None

    # ---------------- Create activities and colleciton ------------------
    common_data = dict(
        duration=timedelta(days=0, seconds=60 * 60 * 1),
        distance=None,
        type_id=1,
        sub_type_id=1,
    )
    activity_1 = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=4, day=1, hour=13),
            name="Collection Activity 1",
            **common_data,  # type: ignore
        ),
        user=user,  # type: ignore
    ).unwrap()
    activity_2 = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2026, month=4, day=2, hour=13),
            name="Collection Activity 2",
            **common_data,  # type: ignore
        ),
        user=user,  # type: ignore
    ).unwrap()
    collection = ActivityCollection(
        user_id=temp_user_id,
        name="Collection",
    )
    collection.activities.extend([activity_1, activity_2])
    db.add(collection)
    db.commit()
    db.refresh(collection)
    collection_id = collection.id
    # -----------------------------------------------------------------
    response = client.delete(
        f"/collection/{collection_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204
    db.expire_all()

    assert db.get(ActivityCollection, collection_id) is None
    assert db.get(Activity, activity_1.id) is not None
    assert db.get(Activity, activity_2.id) is not None


def test_get_collection(
    db: Session,
    client: TestClient,
    user1_id: UUID,
    user1_token: str,
) -> None:
    _collection = db.exec(
        select(ActivityCollection).where(ActivityCollection.user_id == user1_id)
    ).first()
    assert _collection is not None

    response = client.get(
        f"/collection/{_collection.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
