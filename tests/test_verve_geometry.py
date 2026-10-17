import json

import pytest
from pydantic import ValidationError

from verve_backend.schema.verve_file import VerveFeature


@pytest.fixture
def geometry_payload() -> dict:
    return {
        "type": "FeatureCollection",
        "properties": {
            "name": "Geometry contract",
            "activityType": "Cycling",
            "startTime": "2026-10-13T08:00:00Z",
            "durationSeconds": 60,
        },
        "features": [
            {"type": "Feature", "geometry": None, "properties": {"coordTimes": []}}
        ],
    }


@pytest.mark.parametrize("member", ["geometry", "coordTimes"])
def test_geometry_and_timestamps_must_be_present(
    geometry_payload: dict, member: str
) -> None:
    feature = geometry_payload["features"][0]
    container = feature if member == "geometry" else feature["properties"]
    del container[member]
    with pytest.raises(ValidationError) as exc_info:
        VerveFeature.model_validate(geometry_payload)
    expected_location = (
        ("features", 0, "geometry")
        if member == "geometry"
        else ("features", 0, "properties", "coordTimes")
    )
    assert exc_info.value.errors()[0]["loc"] == expected_location


def test_summary_only_serialization_keeps_explicit_null_geometry(
    geometry_payload: dict,
) -> None:
    exported = json.loads(VerveFeature.model_validate(geometry_payload).to_json())
    assert exported["features"][0]["geometry"] is None
    assert exported["features"][0]["properties"]["coordTimes"] == []


@pytest.mark.parametrize("size", [0, 1])
def test_spatial_lines_need_at_least_two_positions(
    geometry_payload: dict, size: int
) -> None:
    feature = geometry_payload["features"][0]
    feature["geometry"] = {
        "type": "LineString",
        "coordinates": [[11, 48, -5]] * size,
    }
    feature["properties"]["coordTimes"] = ["2026-10-13T08:00:00Z"] * size
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)


def test_two_position_lines_preserve_sensor_nulls_and_zero(
    geometry_payload: dict,
) -> None:
    feature = geometry_payload["features"][0]
    feature["geometry"] = {
        "type": "LineString",
        "coordinates": [[11, 48, -5], [11.001, 48.001, 0]],
    }
    feature["properties"] = {
        "coordTimes": ["2026-10-13T08:00:00Z", "2026-10-13T08:01:00Z"],
        "heartRates": [None, 0],
    }
    exported = json.loads(VerveFeature.model_validate(geometry_payload).to_json())
    assert len(exported["features"][0]["geometry"]["coordinates"]) == 2
    assert exported["features"][0]["properties"]["heartRates"] == [None, 0]


@pytest.mark.parametrize("sensor", ["heartRates", "cadences", "powers", "temperatures"])
@pytest.mark.parametrize("spatial", [False, True], ids=["nonspatial", "spatial"])
def test_sensor_arrays_must_match_timestamps(
    geometry_payload: dict, sensor: str, spatial: bool
) -> None:
    feature = geometry_payload["features"][0]
    if spatial:
        feature["geometry"] = {
            "type": "LineString",
            "coordinates": [[11, 48, -5], [11.001, 48.001, 0]],
        }
    feature["properties"]["coordTimes"] = [
        "2026-10-13T08:00:00Z",
        "2026-10-13T08:01:00Z",
    ]
    feature["properties"][sensor] = [None]
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)


def test_feature_collection_requires_a_feature(geometry_payload: dict) -> None:
    geometry_payload["features"] = []
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)


def test_spatial_coordinates_must_match_timestamps(geometry_payload: dict) -> None:
    feature = geometry_payload["features"][0]
    feature["geometry"] = {
        "type": "LineString",
        "coordinates": [[11, 48, -5], [11.001, 48.001, 0]],
    }
    feature["properties"]["coordTimes"] = ["2026-10-13T08:00:00Z"]
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)


@pytest.mark.parametrize("sensor", ["heartRates", "cadences", "powers", "temperatures"])
def test_summary_only_accepts_empty_sensor_arrays(
    geometry_payload: dict, sensor: str
) -> None:
    geometry_payload["features"][0]["properties"][sensor] = []
    exported = json.loads(VerveFeature.model_validate(geometry_payload).to_json())
    feature = exported["features"][0]
    assert feature["geometry"] is None
    assert feature["properties"]["coordTimes"] == []
    assert feature["properties"][sensor] == []
