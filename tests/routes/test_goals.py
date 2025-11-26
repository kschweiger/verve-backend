from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend import crud
from verve_backend.enums import GoalAggregation, GoalType
from verve_backend.models import GoalCreate, GoalPublic, GoalsPublic


# NOTE: Test against the default gaols creating in test setup
@pytest.mark.parametrize(
    ("year", "month", "exp_count"),
    [
        # Load all in 2025
        (2025, None, 3),
        # Load all in Feb 2025
        (2025, 2, 3),
        # Load all in match 2025
        (2025, 3, 2),
        # Load all in Jan 2024
        (2024, 1, 1),
        # Load all in Feb 2024
        (2024, 2, 0),
    ],
)
def test_get_goals(
    client: TestClient,
    user1_token: str,
    year: int,
    month: int | None,
    exp_count: int,
) -> None:
    response = client.get(
        "/goal",
        headers={"Authorization": f"Bearer {user1_token}"},
        params={"year": year, "month": month} if month else {"year": year},
    )

    assert response.status_code == 200
    goals = GoalsPublic.model_validate(response.json())
    assert goals.count == exp_count


def test_add_goal(
    client: TestClient,
    temp_user_token: str,
) -> None:
    goal_data = {
        "name": "New Goal",
        "description": "A newly created goal",
        "target": 15,
        "type": GoalType.ACTIVITY,
        "aggregation": GoalAggregation.DURATION,
    }

    response = client.put(
        "/goal",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=goal_data,
    )

    assert response.status_code == 200
    GoalPublic.model_validate(response.json())


def test_add_goal_invalid_configuration(
    client: TestClient,
    temp_user_token: str,
) -> None:
    goal_data = {
        "name": "New Goal",
        "description": "A newly created goal",
        "target": 15,
        "type": GoalType.MANUAL,
        "aggregation": GoalAggregation.AVG_DISTANCE,
    }

    response = client.put(
        "/goal",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=goal_data,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("attr", "value", "exp_attr"),
    [
        (
            "name",
            "New Name",
            {
                "name": "New Name",
                "description": "A goal to be modified",
                "target": 10,
            },
        ),
        (
            "description",
            "New Description",
            {
                "name": "Modify Goal",
                "description": "New Description",
                "target": 10,
            },
        ),
        (
            "target",
            20,
            {
                "name": "Modify Goal",
                "description": "A goal to be modified",
                "target": 20,
            },
        ),
    ],
)
def test_update_goal(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
    attr: str,
    value: str | int,
    exp_attr: dict[str, Any],
) -> None:
    _goal = crud.create_goal(
        session=db,
        goal=GoalCreate(
            name="Modify Goal",
            description="A goal to be modified",
            target=10,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
        ),
        user_id=temp_user_id,
    ).unwrap()

    response = client.post(
        f"/goal/{_goal.id}/update",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"attribute": attr, "value": value},
    )

    assert response.status_code == 200
    _response_goal = GoalPublic.model_validate(response.json())
    for key, value in exp_attr.items():
        assert getattr(_response_goal, key) == value


def test_modify_manual_goal(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    _goal = crud.create_goal(
        session=db,
        goal=GoalCreate(
            name="Modify Manual Goal",
            description="A manual goal to be modified",
            target=50,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
        ),
        user_id=temp_user_id,
    ).unwrap()

    # Increase by 10
    response = client.get(
        f"/goal/{_goal.id}/modify_amount",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"increase": True, "amount": 10},
    )
    assert response.status_code == 200
    _response_goal = GoalPublic.model_validate(response.json())
    assert _response_goal.current == 10

    # Decrease by 5
    response = client.get(
        f"/goal/{_goal.id}/modify_amount",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"increase": False, "amount": 5},
    )
    assert response.status_code == 200
    _response_goal = GoalPublic.model_validate(response.json())
    assert _response_goal.current == 5


def test_modify_manual_goal_floor(
    client: TestClient,
    db: Session,
    temp_user_id: UUID,
    temp_user_token: str,
) -> None:
    _goal = crud.create_goal(
        session=db,
        goal=GoalCreate(
            name="Modify Manual Goal",
            description="A manual goal to be modified",
            target=50,
            current=3,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
        ),
        user_id=temp_user_id,
    ).unwrap()
    # Decrease by 5
    response = client.get(
        f"/goal/{_goal.id}/modify_amount",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        params={"increase": False, "amount": 5},
    )
    assert response.status_code == 200
    _response_goal = GoalPublic.model_validate(response.json())
    assert _response_goal.current == 0
