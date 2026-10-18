"""Swimming wire and internal metadata behavior."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from verve_backend.core.meta_data import SwimmingMetaData, validate_swimming_meta_data
from verve_backend.schema.exporter import _metadata_for_verve_export
from verve_backend.schema.meta_data import SwimmingMetaDataEnvelopeV1
from verve_backend.schema.verve_file import VerveFeature


def envelope(data: dict[str, Any]) -> SwimmingMetaDataEnvelopeV1:
    return SwimmingMetaDataEnvelopeV1.model_validate(
        {"target": "SwimmingMetaData", "version": "1.0", "data": data}
    )


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"lapCount": 3}, id="counts-only"),
        pytest.param({"laps": [{"index": 0}]}, id="details-only"),
        pytest.param({"sets": [{"index": 0, "lapCount": 3}]}, id="set-summary"),
        *[
            pytest.param({field: 0}, id=field)
            for field in (
                "poolLengthMeters",
                "totalStrokeCount",
                "averageSwolf",
                "lapCount",
                "setCount",
            )
        ],
        pytest.param({"lapCount": 0, "laps": []}, id="reported-empty"),
    ],
)
def test_supported_partial_swimming_roundtrip(data: dict[str, Any]) -> None:
    wire = envelope(data)
    core = wire.to_core_meta_data(ZoneInfo("UTC"))
    output = _metadata_for_verve_export(core.model_dump(mode="json"))
    assert isinstance(output, SwimmingMetaDataEnvelopeV1)
    assert output.data.model_dump(by_alias=True, exclude_none=True) == data


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="empty"),
        pytest.param({"custom": 1}, id="unknown-only"),
        pytest.param({"lapCount": None, "laps": []}, id="unavailable-only"),
        pytest.param({"lapCount": 1, "laps": []}, id="count-mismatch"),
        pytest.param({"laps": [{"index": 1}]}, id="one-based-index"),
        pytest.param({"sets": [{"index": 1}]}, id="set-index"),
        pytest.param({"sets": [{"index": 0, "lapStartIndex": 0}]}, id="missing-laps"),
        pytest.param(
            {"laps": [{"index": 0}], "sets": [{"index": 0, "lapEndIndex": 1}]},
            id="outside-laps",
        ),
        pytest.param(
            {
                "laps": [{"index": 0}],
                "sets": [
                    {"index": 0, "lapStartIndex": 0, "lapEndIndex": 0, "lapCount": 2}
                ],
            },
            id="inclusive-count",
        ),
        pytest.param({"lapCount": -1}, id="negative-count"),
        pytest.param({"lapCount": 1.5}, id="fractional-count"),
        pytest.param({"lapCount": True}, id="boolean-count"),
        pytest.param({"poolLengthMeters": "25"}, id="string-number"),
        pytest.param({"poolLengthMeters": float("inf")}, id="nonfinite"),
        pytest.param({"laps": [None]}, id="null-record"),
    ],
)
def test_invalid_swimming_rejected_by_wire_and_core(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        envelope(data)
    # Convert aliases without validating the invalid values first.
    aliases = {"lapCount": "lap_count", "poolLengthMeters": "pool_length_meters"}
    internal = {aliases.get(key, key): value for key, value in data.items()}
    internal["target"] = "SwimmingMetaData"
    for collection in ("laps", "sets"):
        if collection in internal:
            internal[collection] = [
                None
                if record is None
                else {
                    {
                        "lapStartIndex": "lap_start_index",
                        "lapEndIndex": "lap_end_index",
                        "lapCount": "lap_count",
                    }.get(key, key): value
                    for key, value in record.items()
                }
                for record in internal[collection]
            ]
    with pytest.raises(ValidationError):
        SwimmingMetaData.model_validate(internal)


def file_with_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "features": [{"geometry": None, "properties": {"coordTimes": []}}],
        "properties": {
            "name": "Swim",
            "activityType": "Swimming",
            "startTime": "2026-10-13T08:00:00Z",
            "durationSeconds": 115,
            "metadata": metadata,
        },
    }


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param(
            {"target": "SwimmingMetaData", "data": {"lapCount": 1}},
            id="missing-version",
        ),
        pytest.param(
            {"target": "SwimmingMetaData", "version": "2.0", "data": {"lapCount": 1}},
            id="future-version",
        ),
        pytest.param(
            {
                "target": "SwimmingMetaData",
                "version": "1.0",
                "data": {"laps": [{"index": 2}]},
            },
            id="invalid-data",
        ),
    ],
)
def test_recognized_envelope_cannot_fall_back_to_dictionary(
    metadata: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(file_with_metadata(metadata))


@pytest.mark.parametrize("timestamp", ["2026-10-13T08:00:00", 12345])
def test_swimming_wire_requires_offset_timestamps(timestamp: str | int) -> None:
    with pytest.raises(ValidationError):
        envelope({"laps": [{"index": 0, "startTime": timestamp}]})


def test_fractional_swimming_preserves_elapsed_time_and_reported_precision() -> None:
    data = {
        "poolLengthMeters": 22.86,
        "laps": [
            {
                "index": 0,
                "startTime": "2026-10-13T08:00:00Z",
                "endTime": "2026-10-13T08:00:50Z",
                "durationSeconds": 50.125,
                "distanceMeters": 22.86,
                "strokeCount": 20,
                "swolf": 70.125,
                "restAfterSeconds": 10,
            },
            {
                "index": 1,
                "durationSeconds": 55,
                "distanceMeters": 22.86,
                "strokeCount": 22,
                "swolf": 77,
            },
        ],
        "sets": [
            {
                "index": 0,
                "durationSeconds": 115,
                "distanceMeters": 45.72,
                "lapStartIndex": 0,
                "lapEndIndex": 1,
                "lapCount": 2,
                "averageSwolf": 73.5,
            }
        ],
    }
    wire = envelope(data)
    before = wire.model_dump()
    core = wire.to_core_meta_data(ZoneInfo("Europe/Berlin"))
    output = _metadata_for_verve_export(core.model_dump(mode="json"))
    assert isinstance(output, SwimmingMetaDataEnvelopeV1)
    assert output.data.laps is not None
    assert output.data.sets is not None
    assert core.laps is not None
    assert output.data.pool_length_meters == pytest.approx(22.86)
    assert output.data.laps[0].distance_meters == pytest.approx(22.86)
    assert output.data.laps[0].duration_seconds == pytest.approx(50.125)
    assert output.data.laps[0].swolf == pytest.approx(70.125)
    assert output.data.laps[0].rest_after_seconds == 10
    assert output.data.sets[0].duration_seconds == 115
    assert output.data.sets[0].distance_meters == pytest.approx(45.72)
    assert output.data.sets[0].average_swolf == 73.5
    assert core.laps[0].start_time == datetime(2026, 10, 13, 8, tzinfo=UTC)
    assert wire.model_dump() == before


@pytest.mark.parametrize(
    ("start", "end", "valid"),
    [
        ("2026-10-13T10:00:00+02:00", "2026-10-13T08:00:00Z", True),
        ("2026-10-13T10:00:00+02:00", "2026-10-13T09:00:00+02:00", False),
        (
            datetime(2026, 10, 25, 2, 45, tzinfo=ZoneInfo("Europe/Berlin"), fold=0),
            datetime(2026, 10, 25, 2, 15, tzinfo=ZoneInfo("Europe/Berlin"), fold=1),
            True,
        ),
    ],
)
def test_swimming_interval_order_uses_instants(
    start: str | datetime, end: str | datetime, valid: bool
) -> None:
    data = {"laps": [{"index": 0, "startTime": start, "endTime": end}]}
    if valid:
        envelope(data)
    else:
        with pytest.raises(ValidationError):
            envelope(data)


@pytest.mark.parametrize("field", ["target", "version", "data"])
def test_swimming_envelope_requires_explicit_members(field: str) -> None:
    data = {"target": "SwimmingMetaData", "version": "1.0", "data": {"lapCount": 1}}
    del data[field]
    with pytest.raises(ValidationError):
        SwimmingMetaDataEnvelopeV1.model_validate(data)


def test_swimming_metadata_requires_swimming_activity() -> None:
    data = file_with_metadata(
        {"target": "SwimmingMetaData", "version": "1.0", "data": {"lapCount": 1}}
    )
    data["properties"]["activityType"] = "Cycling"
    with pytest.raises(ValidationError):
        VerveFeature.model_validate(data)


@pytest.mark.parametrize(
    "metadata",
    [{"custom": [1, 2]}, {"target": "AnotherExtension", "version": "2.0", "data": {}}],
)
def test_arbitrary_metadata_remains_supported(metadata: dict[str, Any]) -> None:
    assert (
        VerveFeature.model_validate(file_with_metadata(metadata)).properties.metadata
        == metadata
    )
    assert _metadata_for_verve_export(metadata) == metadata


@pytest.mark.parametrize(
    "data", [{}, {"laps": [], "pool_length_meters": None}, {"custom": "unknown"}]
)
def test_export_omits_unavailable_swimming_envelope(data: dict[str, Any]) -> None:
    assert _metadata_for_verve_export({"target": "SwimmingMetaData", **data}) == {}


def test_export_rejects_malformed_known_metadata() -> None:
    with pytest.raises(ValidationError):
        _metadata_for_verve_export({"target": "SwimmingMetaData", "laps": {}})


@pytest.mark.parametrize("bound", ["lapStartIndex", "lapEndIndex"])
def test_single_set_reference_is_valid(bound: str) -> None:
    metadata = envelope({"laps": [{"index": 0}], "sets": [{"index": 0, bound: 0}]})
    metadata.to_core_meta_data(ZoneInfo("UTC"))


@pytest.mark.parametrize("end", ["2025-01-01T00:40:00+02:00", "2025-01-01T00:20:00"])
def test_core_rejects_reversed_intervals_after_timezone_normalization(end: str) -> None:
    with pytest.raises(ValidationError):
        validate_swimming_meta_data(
            {
                "laps": [
                    {"index": 0, "start_time": "2025-01-01T00:30:00", "end_time": end}
                ]
            },
            ZoneInfo("Europe/Berlin"),
        )


@pytest.mark.parametrize("collection", ["laps", "sets"])
@pytest.mark.parametrize("field", ["durations", "rest_after"])
@pytest.mark.parametrize("value", [True, "1", "1e2"])
def test_core_duration_rejects_boolean_and_numeric_string_coercion(
    collection: str, field: str, value: bool | str
) -> None:
    with pytest.raises(ValidationError):
        validate_swimming_meta_data(
            {collection: [{"index": 0, field: value}]}, ZoneInfo("UTC")
        )
