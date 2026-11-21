from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import Activity, Exercise

PATH = "/strength_training/activity_exercise_plans"
TEMPLATES = "/strength_training/exercise_plans"


@pytest.fixture
def activity_factory(db: Session) -> Generator[Callable[[UUID], UUID]]:
    activities = []

    def create(user_id: UUID) -> UUID:
        activity = Activity(
            user_id=user_id,
            timezone="Europe/Berlin",
            start=datetime.now(timezone.utc),
            distance=1,
            duration=timedelta(minutes=10),
            type_id=1,
            sub_type_id=None,
            name="Snapshot test",
        )
        db.add(activity)
        db.commit()
        activities.append(activity.id)
        return activity.id

    yield create
    for activity_id in activities:
        activity = db.get(Activity, activity_id)
        if activity is not None:
            db.delete(activity)
    db.commit()


def test_apply_copies_entries_independently(
    client: TestClient, user1_token: str, user1_id: UUID, activity_factory, db: Session
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    entries = [
        {"exercise_id": exercise_id, "weight": 10.5, "sets": 3, "repetitions": 8},
        {"exercise_id": exercise_id, "weight": None, "sets": None, "repetitions": None},
    ]
    template = client.post(
        TEMPLATES, headers=headers, json={"name": str(uuid4()), "entries": entries}
    ).json()
    activity_id = activity_factory(user1_id)
    exercise = db.get(Exercise, UUID(exercise_id))
    assert exercise is not None
    exercise.is_active = False
    db.commit()
    try:
        response = client.post(
            f"{PATH}/{activity_id}", headers=headers, params={"plan_id": template["id"]}
        )
        assert response.status_code == 201
        snapshot = response.json()
        assert UUID(snapshot["id"])
        assert snapshot["activity_id"] == str(activity_id)
        assert snapshot["source_plan_id"] == template["id"]
        assert len({entry["id"] for entry in snapshot["entries"]}) == 2
        assert sorted(
            (entry["weight"], entry["sets"], entry["repetitions"])
            for entry in snapshot["entries"]
            if entry["weight"] is not None
        ) == [(10.5, 3, 8)]
        assert any(
            entry["weight"] is None
            and entry["sets"] is None
            and entry["repetitions"] is None
            for entry in snapshot["entries"]
        )
        assert {entry["exercise_id"] for entry in snapshot["entries"]} == {exercise_id}
        updated = client.patch(
            f"{TEMPLATES}/{template['id']}", headers=headers, json={"entries": []}
        )
        assert updated.status_code == 200
        fetched = client.get(f"{PATH}/{activity_id}", headers=headers)
        assert fetched.status_code == 200
        fetched_plan = fetched.json()
        assert {
            key: value for key, value in fetched_plan.items() if key != "entries"
        } == {key: value for key, value in snapshot.items() if key != "entries"}
        assert {entry["id"]: entry for entry in fetched_plan["entries"]} == {
            entry["id"]: entry for entry in snapshot["entries"]
        }
    finally:
        exercise.is_active = True
        db.commit()


def test_concurrent_apply_preserves_winner(
    client: TestClient, user1_token: str, user1_id: UUID, activity_factory
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    template_ids = [
        client.post(TEMPLATES, headers=headers, json={"name": str(uuid4())}).json()[
            "id"
        ]
        for _ in range(2)
    ]
    activity_id = activity_factory(user1_id)

    def apply(template_id: str):
        return client.post(
            f"{PATH}/{activity_id}", headers=headers, params={"plan_id": template_id}
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(apply, template_ids))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner_index = next(
        i for i, response in enumerate(responses) if response.status_code == 201
    )
    winner = responses[winner_index].json()
    assert winner["source_plan_id"] == template_ids[winner_index]
    assert winner["entries"] == []
    assert client.get(f"{PATH}/{activity_id}", headers=headers).json() == winner


def test_missing_and_foreign_activity_or_template(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    user2_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    activity_id = activity_factory(user1_id)
    foreign_activity_id = activity_factory(user2_id)
    template = client.post(
        TEMPLATES, headers=headers, json={"name": str(uuid4())}
    ).json()
    foreign_template = client.post(
        TEMPLATES, headers=other, json={"name": str(uuid4())}
    ).json()
    assert (
        client.post(
            f"{PATH}/{foreign_activity_id}",
            headers=other,
            params={"plan_id": foreign_template["id"]},
        ).status_code
        == 201
    )
    for missing_activity in (uuid4(), foreign_activity_id):
        assert (
            client.post(
                f"{PATH}/{missing_activity}",
                headers=headers,
                params={"plan_id": template["id"]},
            ).status_code
            == 404
        )
        assert (
            client.get(f"{PATH}/{missing_activity}", headers=headers).status_code == 404
        )
    for missing_template in (str(uuid4()), foreign_template["id"]):
        assert (
            client.post(
                f"{PATH}/{activity_id}",
                headers=headers,
                params={"plan_id": missing_template},
            ).status_code
            == 404
        )
    assert client.get(f"{PATH}/{activity_id}", headers=headers).status_code == 404
    assert client.post(f"{PATH}/{activity_id}", headers=headers).status_code == 422


def test_activity_plan_openapi(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    detail = document["paths"][
        "/api/v1/strength_training/activity_exercise_plans/{activity_id}"
    ]
    for operation, success, errors in (
        (detail["post"], "201", ("404", "409")),
        (detail["get"], "200", ("404",)),
    ):
        assert (
            operation["responses"][success]["content"]["application/json"]["schema"][
                "$ref"
            ]
            == "#/components/schemas/ActivityExercisePlanPublic"
        )
        for status in errors:
            assert (
                operation["responses"][status]["content"]["application/json"]["schema"][
                    "$ref"
                ]
                == "#/components/schemas/HTTPErrorResponse"
            )
        assert (
            operation["responses"]["422"]["content"]["application/json"]["schema"][
                "$ref"
            ]
            == "#/components/schemas/HTTPValidationError"
        )
