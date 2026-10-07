from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend import crud
from verve_backend.enums import GoalAggregation, GoalType
from verve_backend.models import (
    GoalCreate,
    LocationPublic,
    RecordsSettings,
    User,
    UserCreate,
    UserPublic,
    UserSettings,
    UserSettingsPublic,
)


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


def test_create_user_no_admin(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.post(
        "/users/create",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=UserCreate(
            name="NewestUser", email="newestuser@mail.com", password="12345678"
        ).model_dump(mode="json"),
    )
    assert response.status_code == 403


def test_create_user_admin(
    client: TestClient,
    admin_token: str,
) -> None:
    response = client.post(
        "/users/create",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=UserCreate(
            name="NewestUser", email="newestuser@mail.com", password="12345678"
        ).model_dump(mode="json"),
    )
    assert response.status_code == 200

    UserPublic.model_validate(response.json())


def test_replace_records_settings(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.get(
        "/users/me/settings",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
    print(response.json())
    settings_pre = UserSettingsPublic.model_validate(response.json()["settings"])

    response = client.patch(
        "/users/me/records_settings",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=RecordsSettings(default_activity_type=2).model_dump(mode="json"),
    )
    assert response.status_code == 200
    response = client.get(
        "/users/me/settings",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert response.status_code == 200
    settings_post = UserSettingsPublic.model_validate(response.json()["settings"])

    assert settings_post.records_settings.default_activity_type == 2
    assert settings_post.records_settings != settings_pre.records_settings


def test_update_timezone(
    client: TestClient,
    temp_user_token: UUID,
) -> None:
    new_tz = "America/Los_Angeles"
    response = client.get(
        "/users/me/settings",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    settings_pre = UserSettingsPublic.model_validate(response.json()["settings"])

    assert settings_pre.timezone != new_tz

    response = client.patch(
        "/users/me/timezone",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"timezone_name": new_tz},
    )
    assert response.status_code == 200
    response = client.get(
        "/users/me/settings",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    settings_post = UserSettingsPublic.model_validate(response.json()["settings"])
    assert settings_post.timezone == new_tz


def test_update_timezone_invalid_name(
    client: TestClient,
    user1_token: str,
) -> None:
    response = client.patch(
        "/users/me/timezone",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"timezone_name": "something/random"},
    )
    assert response.status_code == 422


def test_timezone_change_invalidates_automatic_goal_caches(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
    user1_id: UUID,
) -> None:
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    settings = db.get(UserSettings, temp_user_id)
    assert settings is not None
    assert settings.timezone == "Europe/Berlin"
    response = client.put(
        "/location",
        headers=headers,
        json={"name": "Timezone cache location", "latitude": 1, "longitude": 1},
    )
    assert response.status_code == 200
    location = LocationPublic.model_validate(response.json())
    updated = datetime(2026, 1, 2, 12, tzinfo=UTC)
    automatic_goals = [
        crud.create_goal(
            session=db,
            user_id=temp_user_id,
            goal=GoalCreate(
                name=f"Cached {aggregation}",
                target=10,
                current=2,
                current_updated=updated,
                type=GoalType.ACTIVITY,
                aggregation=aggregation,
            ),
        ).unwrap()
        for aggregation in GoalAggregation
    ]
    for goal_type, active, constraints in [
        (GoalType.LOCATION, True, {"location_id": str(location.id)}),
        (GoalType.ACTIVITY, False, {}),
    ]:
        automatic_goals.append(
            crud.create_goal(
                session=db,
                user_id=temp_user_id,
                goal=GoalCreate(
                    name="Cached automatic goal",
                    target=10,
                    current=2,
                    current_updated=updated,
                    active=active,
                    type=goal_type,
                    aggregation=GoalAggregation.COUNT,
                    constraints=constraints,
                ),
            ).unwrap()
        )
    manual_goal = crud.create_goal(
        session=db,
        user_id=temp_user_id,
        goal=GoalCreate(
            name="Manual progress",
            target=10,
            current=3,
            current_updated=updated,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
        ),
    ).unwrap()
    other_owner_goal = crud.create_goal(
        session=db,
        user_id=user1_id,
        goal=GoalCreate(
            name="Other owner progress",
            target=10,
            current=7,
            current_updated=updated,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.COUNT,
        ),
    ).unwrap()
    manual_updated_before = manual_goal.current_updated
    other_updated_before = other_owner_goal.current_updated
    try:
        response = client.patch(
            "/users/me/timezone",
            headers=headers,
            params={"timezone_name": "America/Los_Angeles"},
        )
        assert response.status_code == 200
        for goal in [*automatic_goals, manual_goal, other_owner_goal]:
            db.refresh(goal)
        db.refresh(settings)
        assert settings.timezone == "America/Los_Angeles"
        assert all(goal.current == 0 for goal in automatic_goals)
        assert all(goal.current_updated is None for goal in automatic_goals)
        assert manual_goal.current == 3
        assert manual_goal.current_updated == manual_updated_before
        assert other_owner_goal.current == 7
        assert other_owner_goal.current_updated == other_updated_before
    finally:
        db.delete(other_owner_goal)
        db.commit()


@pytest.mark.parametrize(
    ("timezone_name", "status_code"),
    [("Europe/Berlin", 200), ("something/random", 422)],
)
def test_timezone_update_preserves_cache_without_valid_change(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
    timezone_name: str,
    status_code: int,
) -> None:
    settings = db.get(UserSettings, temp_user_id)
    assert settings is not None
    timezone_before = settings.timezone
    goal = crud.create_goal(
        session=db,
        user_id=temp_user_id,
        goal=GoalCreate(
            name="Cached progress",
            target=10,
            current=2,
            current_updated=datetime(2026, 1, 2, 12, tzinfo=UTC),
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.COUNT,
        ),
    ).unwrap()
    updated_before = goal.current_updated
    response = client.patch(
        "/users/me/timezone",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"timezone_name": timezone_name},
    )
    assert response.status_code == status_code
    db.refresh(settings)
    db.refresh(goal)
    assert settings.timezone == timezone_before
    assert goal.current == 2
    assert goal.current_updated == updated_before
