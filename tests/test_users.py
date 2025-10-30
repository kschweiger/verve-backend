from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import User, UserPublic


@pytest.mark.parametrize(
    ("update_data", "diff_attr"),
    [
        ({"full_name": "New Full Name"}, {"full_name"}),
        ({"name": "new_name"}, {"name"}),
        ({"email": "new@mail.com"}, {"email"}),
        (
            {"full_name": "New Full Name", "name": "new_name", "email": "new@mail.com"},
            {"full_name", "name", "email"},
        ),
    ],
)
def test_update_user_details(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    update_data: dict,
    diff_attr: set[str],
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    token = client.post(
        "/login/access-token",
        data={"username": user.email, "password": "temporarypassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()["access_token"]

    response = client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json=update_data,
    )

    assert response.status_code == 200
    _response = UserPublic.model_validate(response.json()).model_dump()

    for attr, value in UserPublic.model_validate(user).model_dump().items():
        if attr in diff_attr:
            assert _response[attr] != value
        else:
            assert _response[attr] == value


def test_update_password(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    token = client.post(
        "/login/access-token",
        data={"username": user.email, "password": "temporarypassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()["access_token"]

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "temporarypassword", "new_password": "newtemppassword"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "old_password",
    [
        "wrongpassword",
        "newtemppassword",
    ],
)
def test_update_password_error(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    old_password: str,
) -> None:
    user = db.get(User, temp_user_id)
    assert user is not None
    token = client.post(
        "/login/access-token",
        data={"username": user.email, "password": "temporarypassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()["access_token"]

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": old_password, "new_password": "newtemppassword"},
    )
    assert response.status_code == 400
