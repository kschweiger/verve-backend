import json
from importlib.resources import files
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.core.config import settings
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    LocationSubType,
    LocationType,
    SupportedLocale,
    UserSettings,
)


@pytest.mark.parametrize("locale", list(SupportedLocale))
def test_seeded_types_have_complete_locale_catalogs(
    db: Session, locale: SupportedLocale
) -> None:
    catalog = json.loads(
        files("verve_backend.locales").joinpath(f"{locale}.json").read_text()
    )
    for domain, parent_model, child_model in (
        ("activity_types", ActivityType, ActivitySubType),
        ("location_types", LocationType, LocationSubType),
    ):
        entries = catalog.get(domain, {})
        parents = {
            parent.id: parent.name for parent in db.exec(select(parent_model)).all()
        }
        for name in parents.values():
            label = entries.get(name, {}).get("name")
            assert isinstance(label, str), f"{locale}/{domain}/{name}"
            assert label.strip(), f"{locale}/{domain}/{name}"
            if locale == SupportedLocale.EN:
                assert label == name, f"{locale}/{domain}/{name}: {label!r}"
        for child in db.exec(select(child_model)).all():
            parent = parents[child.type_id]
            label = entries.get(parent, {}).get("sub_types", {}).get(child.name)
            assert isinstance(label, str), f"{locale}/{domain}/{parent}/{child.name}"
            assert label.strip(), f"{locale}/{domain}/{parent}/{child.name}"
            if locale == SupportedLocale.EN:
                assert label == child.name, (
                    f"{locale}/{domain}/{parent}/{child.name}: {label!r}"
                )


@pytest.mark.parametrize(
    ("path", "english", "german", "sub_english", "sub_german"),
    [
        ("/resolve/activity_types", "Cycling", "Radfahren", "Road", "Rennrad"),
        ("/resolve/types", "Cycling", "Radfahren", "Road", "Rennrad"),
        (
            "/resolve/location_types",
            "Facilities",
            "Einrichtungen",
            "Gym",
            "Fitnessstudio",
        ),
    ],
)
def test_resolver_localizes_without_changing_ids_or_relationships(
    client: TestClient,
    path: str,
    english: str,
    german: str,
    sub_english: str,
    sub_german: str,
) -> None:
    default = client.get(path)
    translated = client.get(path, params={"locale": "de"})
    assert default.status_code == translated.status_code == 200
    en_data, de_data = default.json()["data"], translated.json()["data"]
    en_parent = next(item for item in en_data if item["name"] == english)
    de_parent = next(item for item in de_data if item["name"] == german)
    assert en_parent["id"] == de_parent["id"]
    en_sub = next(
        item for item in en_parent["sub_types"] if item["name"] == sub_english
    )
    de_sub = next(item for item in de_parent["sub_types"] if item["name"] == sub_german)
    assert en_sub["id"] == de_sub["id"]
    assert {
        item["id"]: {sub["id"] for sub in item["sub_types"]} for item in en_data
    } == {item["id"]: {sub["id"] for sub in item["sub_types"]} for item in de_data}


@pytest.mark.parametrize(
    "path", ["/resolve/activity_types", "/resolve/types", "/resolve/location_types"]
)
def test_locale_preference_override_and_validation(
    client: TestClient, db: Session, user1_id: UUID, user1_token: str, path: str
) -> None:
    settings = db.get(UserSettings, user1_id)
    assert settings is not None
    original = settings.locale
    settings.locale = SupportedLocale.DE
    db.add(settings)
    db.commit()
    headers = {"Authorization": f"Bearer {user1_token}"}
    try:
        preferred = client.get(path, headers=headers)
        german = client.get(path, headers=headers, params={"locale": "de"})
        english = client.get(path, headers=headers, params={"locale": "en"})
        anonymous = client.get(path)
        assert (
            preferred.status_code
            == german.status_code
            == english.status_code
            == anonymous.status_code
            == 200
        )
        assert preferred.json() == german.json()
        assert english.json() == anonymous.json()
        assert preferred.json() != english.json()
        assert client.get(path, params={"locale": "fr"}).status_code == 422
        assert (
            client.get(path, headers={"Authorization": "Bearer invalid"}).status_code
            == 403
        )
    finally:
        settings.locale = original
        db.add(settings)
        db.commit()


def test_resolvers_are_documented_as_public(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/resolve/activity_types",
        "/resolve/types",
        "/resolve/location_types",
    ):
        assert {} in paths[f"{settings.API_V1_STR}{path}"]["get"]["security"]
    assert {} not in paths[f"{settings.API_V1_STR}/users/me"]["get"]["security"]


def test_missing_translations_fall_back_to_english_then_canonical(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from verve_backend.api.common.locale import load_translations
    from verve_backend.api.routes import resolver

    def translations(locale: SupportedLocale) -> dict:
        result = load_translations(locale)
        if locale == SupportedLocale.DE:
            return {**result, "activity_types": {}}
        return {**result, "activity_types": {"Cycling": {"name": "English cycling"}}}

    monkeypatch.setattr(resolver, "load_translations", translations)
    response = client.get("/resolve/activity_types", params={"locale": "de"})
    assert response.status_code == 200
    cycling = next(
        item for item in response.json()["data"] if item["name"] == "English cycling"
    )
    assert any(item["name"] == "Road" for item in cycling["sub_types"])
