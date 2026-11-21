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
        url = f"{PATH}/{missing_activity}"
        for response in (
            client.post(
                url,
                headers=headers,
                params={"plan_id": template["id"]},
            ),
            client.get(url, headers=headers),
            client.post(
                f"{url}/exercises", headers=headers, json={"exercise_id": str(uuid4())}
            ),
            client.patch(url, headers=headers, json={"entries": []}),
            client.delete(f"{url}/entry", headers=headers, params={"entry_id": 1}),
        ):
            assert response.status_code == 404
            assert response.json() == {"detail": "Activity not found"}
    for missing_template in (str(uuid4()), foreign_template["id"]):
        assert (
            client.post(
                f"{PATH}/{activity_id}",
                headers=headers,
                params={"plan_id": missing_template},
            ).status_code
            == 404
        )
    no_plan = client.get(f"{PATH}/{activity_id}", headers=headers)
    assert no_plan.status_code == 404
    assert no_plan.json() == {"detail": "Activity exercise plan not found"}
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
    prefix = "/api/v1" + PATH + "/{activity_id}"
    for operation, status in (
        (document["paths"][prefix + "/exercises"]["post"], "201"),
        (detail["patch"], "200"),
    ):
        schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/ActivityExercisePlanPublic"
    removal = document["paths"][prefix + "/entry"]["delete"]
    assert "content" not in removal["responses"]["204"]
    entry_id = next(
        param for param in removal["parameters"] if param["name"] == "entry_id"
    )
    assert entry_id["in"] == "query"
    assert entry_id["schema"]["type"] == "integer"


def test_add_entry_creates_or_extends_activity_plan(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    activity_id = activity_factory(user1_id)
    url = f"{PATH}/{activity_id}"
    foreign = client.post(
        f"{url}/exercises",
        headers={"Authorization": f"Bearer {user2_token}"},
        json={"exercise_id": exercise_id},
    )
    assert foreign.status_code == 404
    invalid = client.post(
        f"{url}/exercises", headers=headers, json={"exercise_id": str(uuid4())}
    )
    assert invalid.status_code == 404
    assert client.get(url, headers=headers).status_code == 404

    created = client.post(
        f"{url}/exercises", headers=headers, json={"exercise_id": exercise_id}
    )
    assert created.status_code == 201
    plan = created.json()
    assert plan["activity_id"] == str(activity_id)
    assert plan["source_plan_id"] is None
    added = client.post(
        f"{url}/exercises",
        headers=headers,
        json={"exercise_id": exercise_id, "weight": 12.5},
    )
    assert added.status_code == 201
    assert added.json()["id"] == plan["id"]
    entries = {entry["id"]: entry for entry in added.json()["entries"]}
    original = plan["entries"][0]
    assert entries[original["id"]] == original
    assert len(entries) == 2
    assert {entry["weight"] for entry in entries.values()} == {None, 12.5}


def test_replace_activity_entries_preserves_template_and_link(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    template = client.post(
        TEMPLATES,
        headers=headers,
        json={
            "name": str(uuid4()),
            "entries": [{"exercise_id": exercise_id, "weight": 10}],
        },
    ).json()
    url = f"{PATH}/{activity_factory(user1_id)}"
    attached = client.post(
        url, headers=headers, params={"plan_id": template["id"]}
    ).json()
    foreign = client.patch(
        url, headers={"Authorization": f"Bearer {user2_token}"}, json={"entries": []}
    )
    assert foreign.status_code == 404
    response = client.patch(
        url,
        headers=headers,
        json={"entries": [{"exercise_id": exercise_id, "weight": 15, "sets": 3}]},
    )
    assert response.status_code == 200
    replaced = response.json()
    assert replaced["id"] == attached["id"]
    assert replaced["source_plan_id"] == template["id"]
    assert replaced["entries"][0]["id"] != attached["entries"][0]["id"]
    assert replaced["entries"][0]["weight"] == 15
    assert replaced["entries"][0]["sets"] == 3
    assert client.patch(url, headers=headers, json={"entries": None}).status_code == 422
    assert (
        client.patch(
            url, headers=headers, json={"entries": [{"exercise_id": str(uuid4())}]}
        ).status_code
        == 404
    )
    assert client.get(url, headers=headers).json() == replaced
    assert (
        client.get(f"{TEMPLATES}/{template['id']}", headers=headers).json() == template
    )
    cleared = client.patch(url, headers=headers, json={"entries": []})
    assert cleared.status_code == 200
    assert cleared.json()["entries"] == []


def test_remove_entry_only_affects_its_activity_plan(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    url = f"{PATH}/{activity_factory(user1_id)}"
    other_url = f"{PATH}/{activity_factory(user1_id)}"
    for plan_url in (url, other_url, url):
        response = client.post(
            f"{plan_url}/exercises", headers=headers, json={"exercise_id": exercise_id}
        )
        assert response.status_code == 201
    entries = client.get(url, headers=headers).json()["entries"]
    first, second = entries
    foreign_entry = client.get(other_url, headers=headers).json()["entries"][0]
    for auth, entry_id in ((other, first["id"]), (headers, foreign_entry["id"])):
        response = client.delete(
            f"{url}/entry", headers=auth, params={"entry_id": entry_id}
        )
        assert response.status_code == 404

    deleted = client.delete(
        f"{url}/entry", headers=headers, params={"entry_id": first["id"]}
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(url, headers=headers).json()["entries"] == [second]
    assert client.get(other_url, headers=headers).json()["entries"] == [foreign_entry]
    assert (
        client.delete(
            f"{url}/entry", headers=headers, params={"entry_id": first["id"]}
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"{url}/entry", headers=headers, params={"entry_id": second["id"]}
        ).status_code
        == 204
    )
    assert client.get(url, headers=headers).json()["entries"] == []


def test_muscle_groups_follow_snapshot_and_distinct_exercises(
    client: TestClient, user1_token: str, user1_id: UUID, activity_factory, db: Session
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    exercises = {
        item["code"]: item["id"]
        for item in client.get("/strength_training/exercises", headers=headers).json()[
            "data"
        ]
    }
    chest = exercises["chest_press_machine"]
    shoulder = exercises["shoulder_press_machine"]
    template = client.post(
        TEMPLATES,
        headers=headers,
        json={
            "name": str(uuid4()),
            "entries": [
                {"exercise_id": chest},
                {"exercise_id": chest},
                {"exercise_id": shoulder},
            ],
        },
    ).json()
    url = f"{PATH}/{activity_factory(user1_id)}"
    assert (
        client.post(
            url, headers=headers, params={"plan_id": template["id"]}
        ).status_code
        == 201
    )
    exercise = db.get(Exercise, UUID(chest))
    assert exercise is not None
    exercise.is_active = False
    db.commit()
    try:
        assert (
            client.patch(
                f"{TEMPLATES}/{template['id']}", headers=headers, json={"entries": []}
            ).status_code
            == 200
        )
        response = client.get(f"{url}/muscle_groups", headers=headers)
        assert response.status_code == 200
        groups = {group["code"]: group for group in response.json()["data"]}
        assert len(groups) == len(response.json()["data"])
        front = groups["front_shoulders"]
        assert front["role"] == "primary"
        assert front["exercise_count"] == 2
        assert len(front["exercise_ids"]) == 2
        assert set(front["exercise_ids"]) == {chest, shoulder}
        assert (
            client.patch(
                url, headers=headers, json={"entries": [{"exercise_id": chest}]}
            ).status_code
            == 200
        )
        groups = {
            group["code"]: group
            for group in client.get(f"{url}/muscle_groups", headers=headers).json()[
                "data"
            ]
        }
        assert groups["front_shoulders"]["role"] == "secondary"
        assert groups["front_shoulders"]["exercise_count"] == 1
        assert groups["front_shoulders"]["exercise_ids"] == [chest]
    finally:
        exercise.is_active = True
        db.commit()


def test_muscle_groups_access_and_empty_plan(
    client: TestClient,
    user1_token: str,
    user1_id: UUID,
    user2_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    for activity_id in (uuid4(), activity_factory(user2_id)):
        response = client.get(f"{PATH}/{activity_id}/muscle_groups", headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Activity not found"}
    activity_id = activity_factory(user1_id)
    url = f"{PATH}/{activity_id}"
    response = client.get(f"{url}/muscle_groups", headers=headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Activity exercise plan not found"}
    template = client.post(
        TEMPLATES, headers=headers, json={"name": str(uuid4())}
    ).json()
    assert (
        client.post(
            url, headers=headers, params={"plan_id": template["id"]}
        ).status_code
        == 201
    )
    response = client.get(f"{url}/muscle_groups", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"data": []}


def test_muscle_groups_locale_and_fallback(
    client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    activity_factory,
    db: Session,
    mocker,
) -> None:
    from verve_backend.api.common.locale import load_translations
    from verve_backend.api.routes import strength_training
    from verve_backend.models import SupportedLocale, UserSettings

    settings = db.get(UserSettings, temp_user_id)
    assert settings is not None
    settings.locale = SupportedLocale.DE
    db.commit()
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    chest = next(
        item["id"]
        for item in client.get("/strength_training/exercises", headers=headers).json()[
            "data"
        ]
        if item["code"] == "chest_press_machine"
    )
    url = f"{PATH}/{activity_factory(temp_user_id)}"
    assert (
        client.post(
            f"{url}/exercises", headers=headers, json={"exercise_id": chest}
        ).status_code
        == 201
    )

    def groups(query: str = "") -> dict:
        response = client.get(f"{url}/muscle_groups{query}", headers=headers)
        assert response.status_code == 200
        return {group["code"]: group for group in response.json()["data"]}

    assert groups()["front_shoulders"]["name"] == "Vordere Schultern"
    assert groups("?locale=en")["front_shoulders"]["name"] == "Front shoulders"

    def translations(locale):
        result = load_translations(locale)
        result = {**result, "muscle_groups": {**result["muscle_groups"]}}
        if locale == SupportedLocale.DE:
            result["muscle_groups"].pop("front_shoulders", None)
        return result

    translation_mock = mocker.patch.object(
        strength_training, "load_translations", side_effect=translations
    )
    assert groups("?locale=de")["front_shoulders"]["name"] == "Front shoulders"

    def no_group_label(locale):
        result = translations(locale)
        result["muscle_groups"].pop("front_shoulders", None)
        return result

    translation_mock.side_effect = no_group_label
    assert groups("?locale=de")["front_shoulders"]["name"] == "front_shoulders"


def test_muscle_groups_openapi(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/api/v1" + PATH + "/{activity_id}/muscle_groups"][
        "get"
    ]
    responses = operation["responses"]
    components = document["components"]["schemas"]
    wrapper_ref = responses["200"]["content"]["application/json"]["schema"]["$ref"]
    wrapper = components[wrapper_ref.rsplit("/", 1)[-1]]
    assert wrapper["type"] == "object"
    assert (
        wrapper["properties"]["data"]["items"]["$ref"]
        == "#/components/schemas/ActivityMuscleGroupPublic"
    )
    assert (
        responses["404"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/HTTPErrorResponse"
    )
    assert (
        responses["422"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/HTTPValidationError"
    )
    fields = document["components"]["schemas"]["ActivityMuscleGroupPublic"][
        "properties"
    ]
    assert set(fields) == {
        "id",
        "code",
        "name",
        "role",
        "exercise_count",
        "exercise_ids",
    }


def test_save_activity_as_new_template(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    name = str(uuid4())
    original = client.post(TEMPLATES, headers=headers, json={"name": name}).json()
    url = f"{PATH}/{activity_factory(user1_id)}"
    action = f"{url}/save_as_template"
    missing = client.post(action, headers=headers, json={"name": str(uuid4())})
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Activity exercise plan not found"}
    assert (
        client.post(
            url, headers=headers, params={"plan_id": original["id"]}
        ).status_code
        == 201
    )
    entry = {"exercise_id": exercise_id, "weight": 12.5, "sets": 3, "repetitions": None}
    added = client.post(f"{url}/exercises", headers=headers, json=entry)
    assert added.status_code == 201
    activity_plan = added.json()
    assert client.post(action, headers=headers, json={"name": name}).status_code == 409
    assert client.get(url, headers=headers).json()["source_plan_id"] == original["id"]
    new_name = str(uuid4())
    response = client.post(action, headers=other, json={"name": new_name})
    assert response.status_code == 404
    assert response.json() == {"detail": "Activity not found"}

    response = client.post(action, headers=headers, json={"name": new_name})
    assert response.status_code == 201
    saved = response.json()
    assert saved["id"] != original["id"]
    assert saved["name"] == new_name
    assert len(saved["entries"]) == 1
    assert {key: saved["entries"][0][key] for key in entry} == entry
    assert client.get(url, headers=headers).json() == {
        **activity_plan,
        "source_plan_id": saved["id"],
    }
    assert client.get(f"{TEMPLATES}/{saved['id']}", headers=headers).json() == saved
    assert (
        client.get(f"{TEMPLATES}/{original['id']}", headers=headers).json() == original
    )
    assert client.get(
        f"{TEMPLATES}/{original['id']}/activities", headers=headers
    ).json() == {"data": []}
    linked = client.get(f"{TEMPLATES}/{saved['id']}/activities", headers=headers).json()
    assert {activity["id"] for activity in linked["data"]} == {
        activity_plan["activity_id"]
    }


def test_update_linked_template_keeps_other_activity_entries(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    template = client.post(
        TEMPLATES,
        headers=headers,
        json={
            "name": str(uuid4()),
            "entries": [{"exercise_id": exercise_id, "weight": 10}],
        },
    ).json()
    url = f"{PATH}/{activity_factory(user1_id)}"
    other_url = f"{PATH}/{activity_factory(user1_id)}"
    unlinked_url = f"{PATH}/{activity_factory(user1_id)}"
    for linked_url in (url, other_url):
        assert (
            client.post(
                linked_url, headers=headers, params={"plan_id": template["id"]}
            ).status_code
            == 201
        )
    other_snapshot = client.get(other_url, headers=headers).json()
    assert (
        client.post(
            f"{unlinked_url}/exercises",
            headers=headers,
            json={"exercise_id": exercise_id},
        ).status_code
        == 201
    )
    assert (
        client.post(f"{unlinked_url}/update_template", headers=headers).status_code
        == 409
    )
    assert client.post(f"{url}/update_template", headers=other).status_code == 404

    entry = {"exercise_id": exercise_id, "weight": 20, "sets": None, "repetitions": 8}
    updated = client.patch(url, headers=headers, json={"entries": [entry]})
    assert updated.status_code == 200
    response = client.post(f"{url}/update_template", headers=headers)
    assert response.status_code == 200
    saved = response.json()
    assert saved["id"] == template["id"]
    assert saved["name"] == template["name"]
    assert len(saved["entries"]) == 1
    assert saved["entries"][0]["id"] != template["entries"][0]["id"]
    assert {key: saved["entries"][0][key] for key in entry} == entry
    assert client.get(f"{TEMPLATES}/{template['id']}", headers=headers).json() == saved
    assert client.get(url, headers=headers).json() == updated.json()
    assert client.get(other_url, headers=headers).json() == other_snapshot


def test_template_activities_lists_explicit_links(
    client: TestClient,
    user1_token: str,
    user2_token: str,
    user1_id: UUID,
    activity_factory,
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    other = {"Authorization": f"Bearer {user2_token}"}
    exercise_id = client.get("/strength_training/exercises", headers=headers).json()[
        "data"
    ][0]["id"]
    entry = {"exercise_id": exercise_id}
    plan_ids = [
        client.post(
            TEMPLATES, headers=headers, json={"name": str(uuid4()), "entries": [entry]}
        ).json()["id"]
        for _ in range(2)
    ]
    url = f"{TEMPLATES}/{plan_ids[0]}/activities"
    assert client.get(url, headers=headers).json() == {"data": []}
    original, edited, other_template, unlinked = (
        activity_factory(user1_id) for _ in range(4)
    )
    for activity_id, plan_id in (
        (original, plan_ids[0]),
        (edited, plan_ids[0]),
        (other_template, plan_ids[1]),
    ):
        assert (
            client.post(
                f"{PATH}/{activity_id}", headers=headers, params={"plan_id": plan_id}
            ).status_code
            == 201
        )
    assert (
        client.patch(
            f"{PATH}/{edited}", headers=headers, json={"entries": []}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{PATH}/{unlinked}/exercises", headers=headers, json=entry
        ).status_code
        == 201
    )
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    activities = response.json()["data"]
    assert len(activities) == 2
    assert {item["id"] for item in activities} == {str(original), str(edited)}
    assert client.get(url, headers=other).status_code == 404
    assert (
        client.get(f"{TEMPLATES}/{uuid4()}/activities", headers=headers).status_code
        == 404
    )
