import copy
import json
from importlib.resources import files

import pytest


def document() -> dict:
    return {
        "schema_version": 1,
        "source": "test_catalog",
        "muscles": ["quadriceps", "test_core", "test_unused"],
        "muscle_groups": [
            {"code": "test_legs", "muscles": ["quadriceps"]},
            {"code": "test_empty", "muscles": []},
        ],
        "exercises": [
            {
                "code": "test_squat",
                "primary_muscles": ["quadriceps"],
                "secondary_muscles": ["test_core"],
            },
            {"code": "test_unmapped", "primary_muscles": [], "secondary_muscles": []},
        ],
    }


def test_load_catalog_and_canonical_hash(tmp_path) -> None:
    from verve_backend.core.exercise_catalog_data import load_catalog

    path = tmp_path / "catalog.json"
    raw = document()
    path.write_text(json.dumps(raw))
    first = load_catalog(path)
    raw["$schema"] = "https://example.invalid/not-fetched.json"
    path.write_text(json.dumps(raw, sort_keys=True, indent=4))
    second = load_catalog(path)
    assert first.content_hash == second.content_hash
    assert first.catalog_code == "test_catalog"
    assert first.exercises[0].is_active
    assert first.exercises[0].muscles == {
        "quadriceps": "primary",
        "test_core": "secondary",
    }
    raw["muscle_groups"][0]["muscles"] = []
    path.write_text(json.dumps(raw))
    assert load_catalog(path).content_hash != first.content_hash


@pytest.mark.parametrize(
    "case",
    [
        "extra",
        "version",
        "type",
        "exercise_duplicate",
        "group_duplicate",
        "unknown_muscle",
        "unknown_member",
        "both_roles",
        "duplicate_role",
        "upstream",
    ],
)
def test_invalid_catalog_is_rejected(tmp_path, case) -> None:
    from verve_backend.core.exercise_catalog_data import load_catalog

    raw = document()
    if case == "extra":
        raw["typo"] = True
    elif case == "version":
        raw["schema_version"] = 2
    elif case == "type":
        raw["exercises"][0]["is_active"] = "true"
    elif case == "exercise_duplicate":
        raw["exercises"].append(copy.deepcopy(raw["exercises"][0]))
    elif case == "group_duplicate":
        raw["muscle_groups"].append({"code": "test_legs", "muscles": []})
    elif case == "unknown_muscle":
        raw["exercises"][0]["primary_muscles"] = ["missing"]
    elif case == "unknown_member":
        raw["muscle_groups"][0]["muscles"] = ["missing"]
    elif case == "both_roles":
        raw["exercises"][0]["secondary_muscles"] = ["quadriceps"]
    elif case == "duplicate_role":
        raw["exercises"][0]["primary_muscles"] *= 2
    else:
        raw["exercises"][0]["upstream_id"] = "External"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match=r".+"):
        load_catalog(path)


@pytest.mark.parametrize(
    "text", ['{"source":"a","source":"b"}', '{"schema_version":NaN}', "{broken"]
)
def test_invalid_json_is_rejected(tmp_path, text) -> None:
    from verve_backend.core.exercise_catalog_data import load_catalog

    path = tmp_path / "catalog.json"
    path.write_text(text)
    with pytest.raises(ValueError, match=r".+"):
        load_catalog(path)


def test_empty_assignments_and_overlapping_groups(tmp_path) -> None:
    from verve_backend.core.exercise_catalog_data import load_catalog

    raw = document()
    raw["muscle_groups"][1]["muscles"] = ["quadriceps"]
    raw["exercises"][0]["primary_muscles"].append("test_unused")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw))
    assert len(load_catalog(path).exercises[0].muscles) == 3
    raw["exercises"] = []
    raw["muscle_groups"] = []
    raw["muscles"] = []
    path.write_text(json.dumps(raw))
    assert load_catalog(path).exercises == ()


def test_bundle_and_locale_coverage(monkeypatch, tmp_path) -> None:
    from jsonschema import Draft202012Validator

    from verve_backend.core.exercise_catalog_data import load_catalog

    monkeypatch.chdir(tmp_path)
    resources = files("verve_backend").joinpath("data")
    schema = json.loads(resources.joinpath("exercise_catalog.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(json.loads(resources.joinpath("exercise_catalog.json").read_text()))
    catalog = load_catalog()
    for language in ("en", "de"):
        labels = json.loads(
            files("verve_backend.locales").joinpath(f"{language}.json").read_text()
        )
        for section, codes in (
            ("exercises", {item.code for item in catalog.exercises}),
            ("muscles", set(catalog.muscles)),
            ("muscle_groups", {item.code for item in catalog.groups}),
        ):
            assert codes <= labels[section].keys()
            assert all(labels[section][code].strip() for code in codes)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        pytest.param(None, "schema_version", True, id="boolean-version"),
        pytest.param(None, "source", "Bad Code", id="invalid-code"),
        pytest.param(None, "$schema", None, id="null-schema-hint"),
        pytest.param(None, "upstream", None, id="null-upstream"),
        pytest.param("exercises", "upstream_id", None, id="null-upstream-id"),
        pytest.param("exercises", "is_active", 1, id="integer-activation"),
        pytest.param(
            "exercises",
            "primary_muscles",
            ["quadriceps", "quadriceps"],
            id="duplicate-primary",
        ),
        pytest.param(
            "muscle_groups",
            "muscles",
            ["quadriceps", "quadriceps"],
            id="duplicate-member",
        ),
        pytest.param(
            None, "muscles", ["quadriceps", "quadriceps"], id="duplicate-muscle"
        ),
    ],
)
def test_schema_and_runtime_reject_invalid_shapes(
    tmp_path, section, field, value
) -> None:
    from jsonschema import Draft202012Validator, ValidationError

    from verve_backend.core.exercise_catalog_data import load_catalog

    raw = document()
    target = raw if section is None else raw[section][0]
    target[field] = value
    schema = json.loads(
        files("verve_backend")
        .joinpath("data", "exercise_catalog.schema.json")
        .read_text()
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match=r".+"):
        load_catalog(path)
