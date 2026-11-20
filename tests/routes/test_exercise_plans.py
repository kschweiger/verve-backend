from uuid import uuid4

from fastapi.testclient import TestClient

PATH = "/strength_training/exercise_plans"


def test_create_read_and_list_plans(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]
    name = f"Plan {uuid4()}"
    entries = [
        {"exercise_id": exercise["id"], "weight": 10},
        {"exercise_id": exercise["id"]},
    ]
    created = client.post(
        PATH, headers=headers, json={"name": name, "entries": entries}
    )
    assert created.status_code == 201
    plan = created.json()
    assert plan["name"] == name
    assert len({entry["id"] for entry in plan["entries"]}) == 2
    assert client.get(f"{PATH}/{plan['id']}", headers=headers).json() == plan
    earlier = client.post(PATH, headers=headers, json={"name": f"A {name}"}).json()
    listing = client.get(PATH, headers=headers).json()["data"]
    assert plan in listing
    assert listing.index(earlier) < listing.index(plan)
    assert [item["name"] for item in listing] == sorted(
        item["name"] for item in listing
    )
    assert client.get(f"{PATH}/{plan['id']}", headers=other).status_code == 404
    assert client.post(PATH, headers=headers, json={"name": name}).status_code == 409
    other_plan = client.post(PATH, headers=other, json={"name": name}).json()
    assert other_plan["id"] not in {item["id"] for item in listing}
    other_listing = client.get(PATH, headers=other).json()["data"]
    assert plan["id"] not in {item["id"] for item in other_listing}
    assert other_plan in other_listing
    assert (
        client.post(
            f"{PATH}/{plan['id']}", headers=other, params={"name": "copy"}
        ).status_code
        == 404
    )


def test_plan_response_openapi(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    collection = paths["/api/v1/strength_training/exercise_plans"]
    detail = paths["/api/v1/strength_training/exercise_plans/{plan_id}"]
    for operation, status in [(collection["post"], "201"), (detail["get"], "200")]:
        schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/ExercisePlanPublic"
    assert "content" not in detail["delete"]["responses"]["204"]
    patch = detail["patch"]
    schema = document["components"]["schemas"]["ExercisePlanUpdate"]
    assert not schema.get("required")
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["entries"]["type"] == "array"
    for operation, statuses in [
        (collection["post"], ("404", "409")),
        (detail["get"], ("404",)),
        (patch, ("404", "409")),
        (detail["post"], ("404", "409")),
        (detail["delete"], ("404",)),
    ]:
        for status in statuses:
            error = operation["responses"][status]["content"]["application/json"][
                "schema"
            ]
            assert error["$ref"] == "#/components/schemas/HTTPErrorResponse"
        validation = operation["responses"]["422"]["content"]["application/json"][
            "schema"
        ]
        assert validation["$ref"] == "#/components/schemas/HTTPValidationError"


def test_update_replace_clear_and_rollback(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    plan = client.post(
        PATH,
        headers=headers,
        json={"name": str(uuid4()), "entries": [{"exercise_id": exercise}]},
    ).json()
    url = f"{PATH}/{plan['id']}"
    new_name = str(uuid4())
    renamed = client.patch(url, headers=headers, json={"name": new_name})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == new_name
    assert renamed.json()["entries"] == plan["entries"]
    replaced = client.patch(
        url, headers=headers, json={"entries": [{"exercise_id": exercise, "sets": 3}]}
    )
    assert replaced.status_code == 200
    assert replaced.json()["entries"][0]["id"] != plan["entries"][0]["id"]
    assert replaced.json()["entries"][0]["sets"] == 3
    assert (
        client.patch(
            url, headers=headers, json={"entries": [{"exercise_id": str(uuid4())}]}
        ).status_code
        == 404
    )
    assert client.get(url, headers=headers).json() == replaced.json()
    conflicting = str(uuid4())
    assert (
        client.post(PATH, headers=headers, json={"name": conflicting}).status_code
        == 201
    )
    assert (
        client.patch(
            url, headers=headers, json={"name": conflicting, "entries": []}
        ).status_code
        == 409
    )
    assert client.get(url, headers=headers).json() == replaced.json()
    assert client.patch(url, headers=other, json={"name": "foreign"}).status_code == 404
    assert client.patch(url, headers=headers, json={"name": None}).status_code == 422
    assert client.patch(url, headers=headers, json={"entries": None}).status_code == 422
    assert (
        client.patch(url, headers=headers, json={"entries": []}).json()["entries"] == []
    )


def test_duplicate_and_delete_plan(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    plan = client.post(
        PATH,
        headers=headers,
        json={
            "name": str(uuid4()),
            "entries": [
                {"exercise_id": exercise, "weight": 4, "sets": 2, "repetitions": 8}
            ],
        },
    ).json()
    url = f"{PATH}/{plan['id']}"
    copy_name = str(uuid4())
    copy = client.post(url, headers=headers, params={"name": copy_name})
    assert copy.status_code == 201
    duplicate = copy.json()
    assert duplicate["id"] != plan["id"]
    assert duplicate["entries"][0]["id"] != plan["entries"][0]["id"]
    assert {k: v for k, v in duplicate["entries"][0].items() if k != "id"} == {
        k: v for k, v in plan["entries"][0].items() if k != "id"
    }
    assert (
        client.post(url, headers=headers, params={"name": copy_name}).status_code == 409
    )
    assert client.delete(url, headers=other).status_code == 404
    deleted = client.delete(url, headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"{PATH}/{duplicate['id']}", headers=headers).status_code == 200
    assert client.delete(url, headers=headers).status_code == 404


def test_inactive_exercises_can_be_retained_and_copied(
    client: TestClient, user1_token: str, db
) -> None:
    from uuid import UUID

    from verve_backend.models import Exercise

    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    plan = client.post(
        PATH,
        headers=headers,
        json={"name": str(uuid4()), "entries": [{"exercise_id": exercise_id}]},
    ).json()
    exercise = db.get(Exercise, UUID(exercise_id))
    exercise.is_active = False
    db.commit()
    try:
        entry = {"exercise_id": exercise_id, "weight": 12}
        url = f"{PATH}/{plan['id']}"
        assert (
            client.post(
                PATH, headers=headers, json={"name": str(uuid4()), "entries": [entry]}
            ).status_code
            == 404
        )
        assert (
            client.patch(url, headers=headers, json={"entries": [entry]}).status_code
            == 200
        )
        assert (
            client.patch(
                url, headers=headers, json={"entries": [entry, entry]}
            ).status_code
            == 404
        )
        duplicate = client.post(url, headers=headers, params={"name": str(uuid4())})
        assert duplicate.status_code == 201
        assert duplicate.json()["entries"][0]["weight"] == 12
    finally:
        exercise.is_active = True
        db.commit()


def test_deleting_linked_plan_preserves_snapshot(
    client: TestClient, user1_token: str, user1_id, db
) -> None:
    from uuid import UUID

    from sqlmodel import select

    from verve_backend.models import (
        Activity,
        ActivityExercisePlan,
        ActivityExercisePlanEntry,
        ExercisePlanEntry,
    )

    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    plan = client.post(
        PATH,
        headers=headers,
        json={"name": str(uuid4()), "entries": [{"exercise_id": exercise_id}]},
    ).json()
    activity = db.exec(select(Activity).where(Activity.user_id == user1_id)).first()
    snapshot = ActivityExercisePlan(
        user_id=user1_id, activity_id=activity.id, source_plan_id=UUID(plan["id"])
    )
    db.add(snapshot)
    db.flush()
    db.add(
        ActivityExercisePlanEntry(
            user_id=user1_id,
            activity_plan_id=snapshot.id,
            exercise_id=UUID(exercise_id),
            weight=30,
        )
    )
    db.commit()
    snapshot_id = snapshot.id
    try:
        assert client.delete(f"{PATH}/{plan['id']}", headers=headers).status_code == 204
        db.expire_all()
        retained = db.get(ActivityExercisePlan, snapshot_id)
        assert retained is not None
        assert retained.source_plan_id is None
        assert retained.entries[0].weight == 30
        assert not db.exec(
            select(ExercisePlanEntry).where(
                ExercisePlanEntry.plan_id == UUID(plan["id"])
            )
        ).all()
    finally:
        snapshot = db.get(ActivityExercisePlan, snapshot_id)
        if snapshot is not None:
            db.delete(snapshot)
            db.commit()


def test_plan_names_reject_nul(client: TestClient, user1_token: str) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    plan = client.post(PATH, headers=headers, json={"name": str(uuid4())}).json()
    url = f"{PATH}/{plan['id']}"
    assert (
        client.post(PATH, headers=headers, json={"name": "a\u0000b"}).status_code == 422
    )
    assert (
        client.patch(url, headers=headers, json={"name": "a\u0000b"}).status_code == 422
    )
    assert (
        client.post(url, headers=headers, params={"name": "a\u0000b"}).status_code
        == 422
    )


def test_plan_entries_reject_integer_overflow(
    client: TestClient, user1_token: str
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    plan = client.post(PATH, headers=headers, json={"name": str(uuid4())}).json()
    for field in ("sets", "repetitions"):
        entries = [{"exercise_id": exercise, field: 2_147_483_648}]
        assert (
            client.post(
                PATH, headers=headers, json={"name": str(uuid4()), "entries": entries}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"{PATH}/{plan['id']}", headers=headers, json={"entries": entries}
            ).status_code
            == 422
        )
