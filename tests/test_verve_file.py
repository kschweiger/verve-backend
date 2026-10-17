import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from verve_backend.schema.verve_file import VerveFeature


@pytest.fixture
def file_payload() -> dict:
    return {
        "type": "FeatureCollection",
        "properties": {
            "name": "Core file contract",
            "activityType": "Cycling",
            "startTime": "2026-10-13T08:00:00Z",
            "durationSeconds": 60,
        },
        "features": [
            {"type": "Feature", "geometry": None, "properties": {"coordTimes": []}}
        ],
    }


def validate_file(payload: dict, *, json_input: bool) -> VerveFeature:
    if json_input:
        return VerveFeature.model_validate_json(json.dumps(payload))
    return VerveFeature.model_validate(payload)


@pytest.mark.parametrize("json_input", [False, True], ids=["python", "json"])
def test_start_time_requires_an_offset(file_payload: dict, json_input: bool) -> None:
    file_payload["properties"]["startTime"] = "2026-10-13T08:00:00"
    with pytest.raises(ValidationError) as exc_info:
        validate_file(file_payload, json_input=json_input)
    assert exc_info.value.errors()[0]["loc"] == ("properties", "startTime")


@pytest.mark.parametrize(
    "feature_index", [0, 1], ids=["first-feature", "later-feature"]
)
@pytest.mark.parametrize("json_input", [False, True], ids=["python", "json"])
def test_each_coordinate_time_requires_an_offset(
    file_payload: dict, feature_index: int, json_input: bool
) -> None:
    feature = file_payload["features"][0]
    feature["properties"]["coordTimes"] = [
        "2026-10-13T08:00:00Z",
        "2026-10-13T08:01:00Z",
    ]
    file_payload["features"] = [deepcopy(feature) for _ in range(feature_index + 1)]
    file_payload["features"][feature_index]["properties"]["coordTimes"][1] = (
        "2026-10-13T08:01:00"
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_file(file_payload, json_input=json_input)
    assert exc_info.value.errors()[0]["loc"] == (
        "features",
        feature_index,
        "properties",
        "coordTimes",
        1,
    )


@pytest.mark.parametrize("field", ["startTime", "coordTimes"])
def test_core_timestamps_reject_naive_python_datetimes(
    file_payload: dict, field: str
) -> None:
    naive = datetime(2026, 10, 13, 8)
    if field == "startTime":
        file_payload["properties"][field] = naive
    else:
        file_payload["features"][0]["properties"][field] = [naive]
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(file_payload)


@pytest.mark.parametrize("field", ["startTime", "coordTimes"])
def test_display_timezone_does_not_supply_a_timestamp_offset(
    file_payload: dict, field: str
) -> None:
    file_payload["properties"]["timezone"] = "Europe/Berlin"
    if field == "startTime":
        file_payload["properties"][field] = "2026-10-13T08:00:00"
    else:
        file_payload["features"][0]["properties"][field] = ["2026-10-13T08:00:00"]
    with pytest.raises(ValidationError):
        VerveFeature.model_validate_json(json.dumps(file_payload))


@pytest.mark.parametrize("field", ["startTime", "coordTimes"])
@pytest.mark.parametrize(
    "timestamp",
    [1791878400, 1791878400.5, "1791878400"],
    ids=["integer-epoch", "fractional-epoch", "string-epoch"],
)
@pytest.mark.parametrize("json_input", [False, True], ids=["python", "json"])
def test_file_timestamps_reject_epoch_inputs(
    file_payload: dict, field: str, timestamp: int | float | str, json_input: bool
) -> None:
    if field == "startTime":
        file_payload["properties"][field] = timestamp
    else:
        file_payload["features"][0]["properties"][field] = [timestamp]
    with pytest.raises(ValidationError):
        validate_file(file_payload, json_input=json_input)


@pytest.mark.parametrize(
    "timestamp",
    ["2026-10-13T08:00:00Z", "2026-10-13T10:00:00+02:00", "2026-10-13T01:00:00-07:00"],
    ids=["utc", "positive-offset", "negative-offset"],
)
@pytest.mark.parametrize("input_kind", ["json", "python-string", "python-datetime"])
def test_file_timestamps_preserve_instants(
    file_payload: dict, timestamp: str, input_kind: str
) -> None:
    value = (
        datetime.fromisoformat(timestamp)
        if input_kind == "python-datetime"
        else timestamp
    )
    file_payload["properties"]["startTime"] = value
    file_payload["properties"]["timezone"] = "Asia/Tokyo"
    file_payload["features"][0]["properties"]["coordTimes"] = [value]
    model = validate_file(file_payload, json_input=input_kind == "json")
    exported = json.loads(model.to_json())
    assert (
        datetime.fromisoformat(exported["properties"]["startTime"]).utcoffset()
        is not None
    )
    assert (
        datetime.fromisoformat(
            exported["features"][0]["properties"]["coordTimes"][0]
        ).utcoffset()
        is not None
    )
    restored = VerveFeature.model_validate_json(model.to_json())
    expected = datetime(2026, 10, 13, 8, tzinfo=UTC)
    for data in (model, restored):
        assert data.properties.start_time.astimezone(UTC) == expected
        assert data.features[0].properties.coord_times[0].astimezone(UTC) == expected


def test_coordinate_times_preserve_dst_instants(file_payload: dict) -> None:
    file_payload["features"][0]["properties"]["coordTimes"] = [
        "2026-10-25T02:55:00+02:00",
        "2026-10-25T02:00:00+01:00",
    ]
    model = VerveFeature.model_validate_json(json.dumps(file_payload))
    restored = VerveFeature.model_validate_json(model.to_json())
    times = [
        time.astimezone(UTC) for time in restored.features[0].properties.coord_times
    ]
    assert times == [
        datetime(2026, 10, 25, 0, 55, tzinfo=UTC),
        datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
    ]
    assert (times[1] - times[0]).total_seconds() == 300


@pytest.mark.parametrize(
    ("stats", "expected"),
    [
        pytest.param(None, {}, id="omitted-statistics"),
        pytest.param({}, {}, id="empty-statistics"),
        pytest.param({"speed": None}, {}, id="null-metric"),
        pytest.param({"speed": {}}, {"speed": {}}, id="empty-summary"),
        pytest.param(
            {"speed": {"avg": None, "min": None, "max": None}},
            {"speed": {}},
            id="null-summary-values",
        ),
        pytest.param({"speed": {"avg": 10}}, {"speed": {"avg": 10}}, id="only-average"),
        pytest.param({"speed": {"min": 2}}, {"speed": {"min": 2}}, id="only-minimum"),
        pytest.param({"speed": {"max": 12}}, {"speed": {"max": 12}}, id="only-maximum"),
        pytest.param({"speed": {"avg": 0}}, {"speed": {"avg": 0}}, id="zero-average"),
        pytest.param({"speed": {"min": 0}}, {"speed": {"min": 0}}, id="zero-minimum"),
        pytest.param({"speed": {"max": 0}}, {"speed": {"max": 0}}, id="zero-maximum"),
        pytest.param(
            {"heartRate": {"avg": 120}},
            {"heartRate": {"avg": 120}},
            id="partial-heart-rate",
        ),
        pytest.param({"power": {"max": 0}}, {"power": {"max": 0}}, id="partial-power"),
        pytest.param(
            {"cadence": {"min": 0}}, {"cadence": {"min": 0}}, id="partial-cadence"
        ),
    ],
)
def test_optional_statistics_round_trip(
    file_payload: dict, stats: dict | None, expected: dict
) -> None:
    if stats is not None:
        file_payload["properties"]["stats"] = stats
    model = VerveFeature.model_validate_json(json.dumps(file_payload))
    exported = json.loads(model.to_json())
    assert exported["properties"]["stats"] == expected
    restored = VerveFeature.model_validate_json(model.to_json())
    assert json.loads(restored.to_json())["properties"]["stats"] == expected


@pytest.mark.parametrize("sensor", ["heartRates", "cadences", "powers", "temperatures"])
@pytest.mark.parametrize(
    ("present", "readings"),
    [
        pytest.param(False, None, id="omitted-array"),
        pytest.param(True, None, id="null-array"),
        pytest.param(True, [None, 0], id="missing-reading-and-zero"),
    ],
)
def test_nullable_sensor_arrays_round_trip(
    file_payload: dict, sensor: str, present: bool, readings: list | None
) -> None:
    properties = file_payload["features"][0]["properties"]
    properties["coordTimes"] = ["2026-10-13T08:00:00Z", "2026-10-13T08:01:00Z"]
    if present:
        properties[sensor] = readings
    model = VerveFeature.model_validate_json(json.dumps(file_payload))
    restored = VerveFeature.model_validate_json(model.to_json())
    for data in (model, restored):
        feature = json.loads(data.to_json())["features"][0]
        assert feature["geometry"] is None
        assert feature["properties"]["coordTimes"] == [
            "2026-10-13T08:00:00Z",
            "2026-10-13T08:01:00Z",
        ]
        if readings is None:
            assert sensor not in feature["properties"]
        else:
            assert feature["properties"][sensor] == [None, 0]


def test_summary_only_omits_unavailable_optional_fields(file_payload: dict) -> None:
    model = VerveFeature.model_validate_json(json.dumps(file_payload))
    exported = json.loads(model.to_json())
    assert exported["features"][0]["geometry"] is None
    assert exported["features"][0]["properties"] == {"coordTimes": []}
    for member in ("description", "timezone", "equipment", "totalEnergyKcal"):
        assert member not in exported["properties"]


def test_arbitrary_metadata_timestamps_remain_unchanged(file_payload: dict) -> None:
    metadata = {
        "custom": {"startTime": "2026-10-13T08:00:00"},
        "coordTimes": ["2026-10-13T08:00:00"],
    }
    file_payload["properties"]["metadata"] = metadata
    model = VerveFeature.model_validate_json(json.dumps(file_payload))
    restored = VerveFeature.model_validate_json(model.to_json())
    assert restored.properties.metadata == metadata
