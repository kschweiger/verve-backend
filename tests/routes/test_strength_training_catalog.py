from uuid import uuid4

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from verve_backend.core.exercise_catalog_data import load_catalog

PATH = "/strength_training/exercises"


def test_catalog_returns_active_exercises_and_matching_detail(
    client: TestClient, user1_token: str
) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    response = client.get(PATH, headers=headers)
    assert response.status_code == 200
    exercises = response.json()["data"]
    active_codes = {item.code for item in load_catalog().exercises if item.is_active}
    assert {item["code"] for item in exercises} == active_codes
    assert len(exercises) == len(active_codes)
    assert all(e["is_active"] for e in exercises)
    exercise = next(e for e in exercises if e["code"] == "chest_press_machine")
    assert set(exercise) == {"id", "code", "name", "is_active", "muscles"}
    assert {m["role"] for m in exercise["muscles"]} == {"primary", "secondary"}
    assert all(
        set(m) == {"id", "code", "name", "role", "muscle_groups"}
        for m in exercise["muscles"]
    )
    assert all(
        set(g) == {"id", "code", "name"}
        for m in exercise["muscles"]
        for g in m["muscle_groups"]
    )
    assert [m["code"] for m in exercise["muscles"]] == sorted(
        m["code"] for m in exercise["muscles"]
    )
    assert all(
        [g["code"] for g in m["muscle_groups"]]
        == sorted(g["code"] for g in m["muscle_groups"])
        for m in exercise["muscles"]
    )
    assert {
        m["code"]: (m["role"], [g["code"] for g in m["muscle_groups"]])
        for m in exercise["muscles"]
    } == {
        "pectoralis_major": ("primary", ["chest"]),
        "anterior_deltoid": ("secondary", ["front_shoulders"]),
        "triceps_brachii": ("secondary", ["back_upper_arms"]),
    }
    detail = client.get(f"{PATH}/{exercise['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json() == exercise


def test_catalog_errors_and_openapi(client: TestClient, user1_token: str) -> None:
    headers = {"Authorization": f"Bearer {user1_token}"}
    assert client.get(PATH).status_code == 401
    assert client.get(f"{PATH}/{uuid4()}", headers=headers).status_code == 404
    assert client.get(f"{PATH}/invalid", headers=headers).status_code == 422
    schema = client.get("/openapi.json").json()
    operations = schema["paths"]["/api/v1/strength_training/exercises/{exercise_id}"][
        "get"
    ]
    assert {"400", "401", "403", "404", "422"} <= operations["responses"].keys()
    paths = schema["paths"]
    listing = paths["/api/v1/strength_training/exercises"]["get"]
    components = schema["components"]["schemas"]
    ref = lambda response: response["content"]["application/json"]["schema"]["$ref"]
    list_schema = components[ref(listing["responses"]["200"]).rsplit("/", 1)[-1]]
    assert list_schema["type"] == "object"
    assert ref(operations["responses"]["200"]) == "#/components/schemas/ExercisePublic"
    assert (
        list_schema["properties"]["data"]["items"]["$ref"]
        == "#/components/schemas/ExercisePublic"
    )
    assert (
        components["ExercisePublic"]["properties"]["muscles"]["items"]["$ref"]
        == "#/components/schemas/ExerciseMusclePublic"
    )
    muscle = components["ExerciseMusclePublic"]["properties"]
    assert (
        muscle["muscle_groups"]["items"]["$ref"]
        == "#/components/schemas/MuscleGroupPublic"
    )
    assert muscle["role"]["$ref"] == "#/components/schemas/ExerciseMuscleRole"
    assert set(components["ExerciseMuscleRole"]["enum"]) == {"primary", "secondary"}
    assert "primary target" in muscle["role"]["description"]
    assert listing["responses"]["404"]["description"] == "User not found"
    assert (
        ref(operations["responses"]["404"]) == "#/components/schemas/HTTPErrorResponse"
    )
    for operation in (listing, operations):
        locale = next(p for p in operation["parameters"] if p["name"] == "locale")
        assert "preference" in locale["description"]
        assert "English" in locale["description"]


def test_catalog_preserves_historical_exercises_and_falls_back_to_code(
    client: TestClient, user1_token: str, db
) -> None:
    from verve_backend.models import Exercise

    exercise = Exercise(code=f"test_untranslated_{uuid4().hex}", is_active=False)
    db.add(exercise)
    db.commit()
    try:
        headers = {"Authorization": f"Bearer {user1_token}"}
        listing = client.get(PATH, headers=headers).json()["data"]
        assert exercise.code not in [item["code"] for item in listing]
        detail = client.get(f"{PATH}/{exercise.id}?locale=de", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["name"] == exercise.code
        assert detail.json()["muscles"] == []
        assert detail.json()["is_active"] is False
    finally:
        db.delete(exercise)
        db.commit()


def test_catalog_uses_locale_override_and_user_preference(
    client: TestClient, temp_user_id, temp_user_token: str, db
) -> None:
    from verve_backend.models import SupportedLocale, UserSettings

    settings = db.get(UserSettings, temp_user_id)
    assert settings is not None
    settings.locale = SupportedLocale.DE
    db.add(settings)
    db.commit()
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    preferred = client.get(PATH, headers=headers).json()["data"]
    english = client.get(f"{PATH}?locale=en", headers=headers).json()["data"]
    german = client.get(f"{PATH}?locale=de", headers=headers).json()["data"]
    german_by_code = {item["code"]: item for item in german}
    assert {item["code"]: item for item in preferred} == german_by_code
    english_names = {item["code"]: item["name"] for item in english}
    assert english_names.keys() == german_by_code.keys()
    assert any(
        german_by_code[code]["name"] != name for code, name in english_names.items()
    )


def test_missing_german_label_falls_back_to_english(
    client: TestClient, user1_token: str, mocker: MockerFixture
) -> None:
    from verve_backend.api.common.locale import load_translations
    from verve_backend.api.routes import strength_training
    from verve_backend.models import SupportedLocale

    def translations(locale):
        result = load_translations(locale)
        if locale == SupportedLocale.DE:
            result = {**result, "exercises": {**result["exercises"]}}
            result["exercises"].pop("chest_press_machine", None)
        return result

    mocker.patch.object(
        strength_training, "load_translations", side_effect=translations
    )
    headers = {"Authorization": f"Bearer {user1_token}"}
    result = client.get(f"{PATH}?locale=de", headers=headers)
    assert result.status_code == 200
    exercise = next(
        e for e in result.json()["data"] if e["code"] == "chest_press_machine"
    )
    english = load_translations(SupportedLocale.EN)
    assert exercise["name"] == english["exercises"]["chest_press_machine"]
