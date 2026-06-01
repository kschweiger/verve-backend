from importlib import resources

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
