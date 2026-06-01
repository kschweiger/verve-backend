from importlib import resources

from verve_backend.schema.exporter import _metadata_for_verve_export
from verve_backend.schema.meta_data import SwimmingMetaDataEnvelopeV1
from verve_backend.schema.verve_file import VerveFeature


def test_verve_file_parses_swimming_metadata_envelope() -> None:
    with (
        resources.files("tests.resources")
        .joinpath("swimming_verve_file.json")
        .open("rb") as f
    ):
        data = VerveFeature.model_validate_json(f.read())

    metadata = data.properties.metadata

    assert isinstance(metadata, SwimmingMetaDataEnvelopeV1)
    assert metadata.target == "SwimmingMetaData"
    assert metadata.version == "1.0"
    assert metadata.data.pool_length_meters == 50
    assert metadata.data.lap_count == 16
    assert metadata.data.set_count == 10
    assert len(metadata.data.laps or []) == 16
    assert len(metadata.data.sets or []) == 10


def test_swimming_metadata_envelope_exports_camel_case() -> None:
    metadata = SwimmingMetaDataEnvelopeV1.model_validate(
        {
            "target": "SwimmingMetaData",
            "version": "1.0",
            "data": {
                "poolLengthMeters": 25,
                "averageSwolf": 97.1,
                "lapCount": 1,
                "strokeStyles": ["breaststroke"],
                "laps": [
                    {
                        "index": 1,
                        "durationSeconds": 54.3,
                        "strokeStyle": "breaststroke",
                    }
                ],
            },
        }
    )

    assert metadata.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "target": "SwimmingMetaData",
        "version": "1.0",
        "data": {
            "poolLengthMeters": 25.0,
            "averageSwolf": 97.1,
            "lapCount": 1,
            "strokeStyles": ["breaststroke"],
            "laps": [
                {
                    "index": 1,
                    "durationSeconds": 54.3,
                    "strokeStyle": "breaststroke",
                }
            ],
        },
    }


def test_verve_file_dump_serializes_swimming_metadata_envelope() -> None:
    with (
        resources.files("tests.resources")
        .joinpath("swimming_verve_file.json")
        .open("rb") as f
    ):
        data = VerveFeature.model_validate_json(f.read())

    dumped = data.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert dumped["properties"]["metadata"]["target"] == "SwimmingMetaData"
    assert dumped["properties"]["metadata"]["version"] == "1.0"
    assert dumped["properties"]["metadata"]["data"]["poolLengthMeters"] == 50.0


def test_verve_file_accepts_snake_case_and_exports_camel_case() -> None:
    data = VerveFeature.model_validate(
        {
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "coord_times": ["2026-05-27T14:57:40Z"],
                        "heart_rates": [120],
                    },
                }
            ],
            "properties": {
                "verve_version": "1.0",
                "name": "Walk",
                "activity_type": "Foot Sports",
                "activity_sub_type": "Walk",
                "start_time": "2026-05-27T14:57:39Z",
                "duration": 60,
                "moving_duration": 55,
                "distance": 100,
                "energy": 10,
                "elevation_gain": 5,
                "elevation_loss": 4,
                "stats": {"heart_rate": {"avg": 120}},
            },
        }
    )

    dumped = data.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert dumped["features"][0]["properties"]["coordTimes"] == ["2026-05-27T14:57:40Z"]
    assert dumped["features"][0]["properties"]["heartRates"] == [120]
    assert dumped["properties"]["verveVersion"] == "1.0"
    assert dumped["properties"]["activityType"] == "Foot Sports"
    assert dumped["properties"]["activitySubType"] == "Walk"
    assert dumped["properties"]["startTime"] == "2026-05-27T14:57:39Z"
    assert dumped["properties"]["durationSeconds"] == 60.0
    assert dumped["properties"]["movingDurationSeconds"] == 55.0
    assert dumped["properties"]["totalDistanceMeters"] == 100.0
    assert dumped["properties"]["totalEnergyKcal"] == 10.0
    assert dumped["properties"]["elevationGain"] == 5.0
    assert dumped["properties"]["elevationLoss"] == 4.0
    assert dumped["properties"]["stats"]["heartRate"]["avg"] == 120.0


def test_exporter_converts_core_swimming_metadata_to_envelope() -> None:
    metadata = _metadata_for_verve_export(
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "lap_count": 2,
            "set_count": 1,
            "styles": ["freestyle"],
            "laps": [
                {
                    "index": 0,
                    "durations": "PT1M",
                    "distance_meters": 50,
                    "style": "freestyle",
                    "swolf": 30,
                }
            ],
            "sets": [
                {
                    "index": 0,
                    "durations": "PT2M",
                    "distance_meters": 100,
                    "style": "freestyle",
                    "avg_swofl": 30,
                }
            ],
        }
    )
    dumped = metadata.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert dumped["target"] == "SwimmingMetaData"
    assert dumped["version"] == "1.0"
    assert dumped["data"]["poolLengthMeters"] == 50.0
    assert dumped["data"]["lapCount"] == 2
    assert dumped["data"]["setCount"] == 1
    assert dumped["data"]["laps"][0]["durationSeconds"] == 60.0
    assert dumped["data"]["laps"][0]["strokeStyle"] == "freestyle"
    assert dumped["data"]["sets"][0]["averageSwolf"] == 30.0


def test_exporter_keeps_unknown_metadata_raw() -> None:
    metadata = _metadata_for_verve_export({"some": "value"})

    assert metadata == {"some": "value"}
