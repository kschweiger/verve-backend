from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.models import (
    ActivityTag,
    ActivityTagCategory,
    ActivityTagCategoryCreate,
    ActivityTagCategoryPublic,
    ActivityTagCreate,
    ActivityTagPublic,
    ListResponse,
)


def test_create_category(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.put(
        "/tag/category/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCategoryCreate(name="New Category").model_dump(mode="json"),
    )

    assert response.status_code == 200

    ActivityTagCategoryPublic.model_validate(response.json())


def test_create_category_unique_constrain(
    client: TestClient,
    user1_token: str,
    user2_token: str,
) -> None:
    _json = ActivityTagCategoryCreate(name="Another new Category").model_dump(
        mode="json"
    )

    response = client.put(
        "/tag/category/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=_json,
    )

    assert response.status_code == 200

    response = client.put(
        "/tag/category/add",
        headers={"Authorization": f"Bearer {user2_token}"},
        json=_json,
    )

    assert response.status_code == 200

    response = client.put(
        "/tag/category/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=_json,
    )

    assert response.status_code == 400


def test_create_tag_no_cat(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.put(
        "/tag/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCreate(name="New Tag").model_dump(mode="json"),
    )

    assert response.status_code == 200

    _tag = ActivityTagPublic.model_validate(response.json())
    assert _tag.category_id is None
    assert _tag.name == "New Tag"


def test_create_tag_cat(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.put(
        "/tag/category/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCategoryCreate(name="Category for tag").model_dump(mode="json"),
    )
    assert response.status_code == 200

    _cat = ActivityTagCategoryPublic.model_validate(response.json())
    response = client.put(
        "/tag/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCreate(name="Another new tag", category_id=_cat.id).model_dump(
            mode="json"
        ),
    )

    assert response.status_code == 200

    _tag = ActivityTagPublic.model_validate(response.json())
    assert _tag.category_id == _cat.id


def test_create_tag_invalid_cat(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.put(
        "/tag/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCreate(name="New Tag", category_id=99999999).model_dump(
            mode="json"
        ),
    )

    assert response.status_code == 400


def test_get_tags(
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    _tag = db.exec(select(ActivityTag).where(ActivityTag.user_id == user1_id)).first()
    assert _tag is not None

    response = client.get(
        f"/tag/{_tag.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == 200

    res_tag = ActivityTagPublic.model_validate(response.json())
    assert res_tag.name == _tag.name


def test_delete_tag(
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    _tag = db.exec(select(ActivityTag).where(ActivityTag.user_id == user1_id)).first()
    assert _tag is not None

    response = client.delete(
        f"/tag/{_tag.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == 204

    db.reset()
    _tag_after = db.get(ActivityTag, _tag.id)
    assert _tag_after is None


def test_add_tag_to_category(
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    response = client.put(
        "/tag/add",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCreate(name="New Tag").model_dump(mode="json"),
    )

    assert response.status_code == 200

    _tag = ActivityTagPublic.model_validate(response.json())
    assert _tag.category_id is None

    _cat = db.exec(
        select(ActivityTagCategory).where(ActivityTagCategory.user_id == user1_id)
    ).first()
    assert _cat is not None

    response = client.patch(
        f"/tag/category/{_cat.id}/add/{_tag.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=ActivityTagCreate(name="Tag with cat", category_id=_cat.id).model_dump(
            mode="json"
        ),
    )

    assert response.status_code == 204

    updated_tag = db.get(ActivityTag, _tag.id)
    assert updated_tag is not None
    assert updated_tag.category_id == _cat.id


def test_get_all_tags(
    db: Session,
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
) -> None:
    _cat = ActivityTagCategory(name="all_tag_test_cat", user_id=user1_id)
    db.add(_cat)
    db.commit()
    db.refresh(_cat)

    _tag_1 = ActivityTag(
        name="all_tag_test_tag_1", user_id=user1_id, category_id=_cat.id
    )
    _tag_2 = ActivityTag(
        name="all_tag_test_tag_2", user_id=user1_id, category_id=_cat.id
    )
    db.add_all([_tag_1, _tag_2])
    db.commit()
    db.refresh(_tag_1)
    db.refresh(_tag_2)

    response = client.get(
        f"/tag/category/{_cat.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    assert response.status_code == 200

    data = ListResponse[ActivityTagCategoryPublic].model_validate(response.json())

    assert len(data.data) == 2


@pytest.mark.parametrize("cascade", [True, False])
def test_delete_category(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    temp_user_id: UUID,
    cascade: bool,
) -> None:
    pass
    _cat = ActivityTagCategory(name="all_tag_test_cat", user_id=temp_user_id)
    db.add(_cat)
    db.commit()
    db.refresh(_cat)

    _tag_1 = ActivityTag(
        name="all_tag_test_tag_1", user_id=temp_user_id, category_id=_cat.id
    )
    _tag_2 = ActivityTag(
        name="all_tag_test_tag_2", user_id=temp_user_id, category_id=_cat.id
    )
    db.add_all([_tag_1, _tag_2])
    db.commit()
    db.refresh(_tag_1)
    db.refresh(_tag_2)
    response = client.delete(
        f"/tag/category/{_cat.id}",
        params={"cascade": cascade},
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 204

    db.reset()
    _tag_1_after = db.get(ActivityTag, _tag_1.id)
    _tag_2_after = db.get(ActivityTag, _tag_2.id)
    if cascade:
        assert _tag_1_after is None
        assert _tag_2_after is None
    else:
        assert _tag_1_after is not None
        assert _tag_1_after.category_id is None
        assert _tag_2_after is not None
        assert _tag_2_after.category_id is None
