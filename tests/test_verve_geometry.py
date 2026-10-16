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
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)


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
def test_nonspatial_sensor_arrays_must_match_timestamps(
    geometry_payload: dict, sensor: str
) -> None:
    geometry_payload["features"][0]["properties"][sensor] = [None]
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(geometry_payload)
