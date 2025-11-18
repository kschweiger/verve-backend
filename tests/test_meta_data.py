from typing import Any

import pytest

from verve_backend.core.meta_data import (
    ActivityMetaData,
    LapData,
    SwimmingMetaData,
    parse_meta_data,
)


def test_activity_meta_data_target() -> None:
    ActivityMetaData(target="ActivityMetaData")

    with pytest.raises(ValueError):
        ActivityMetaData(target="WrongTarget")


@pytest.mark.parametrize(
    "initial_data",
    [
        SwimmingMetaData(segments=[LapData(count=5, lap_lenths=50, style="freestyle")]),
    ],
)
def test_parse_meta_data(
    initial_data: ActivityMetaData,
) -> None:
    raw_data = initial_data.model_dump(mode="json")
    validated_data = parse_meta_data(raw_data)
    assert isinstance(validated_data, type(initial_data))


@pytest.mark.parametrize(
    "raw_data",
    [
        {"segments": [{"count": 10}]},
        {"target": "SwimmingMetaData", "segments": [{"style": "freestyle"}]},
    ],
)
def test_parse_meta_data_invalid(raw_data: dict[str, Any]) -> None:
    assert parse_meta_data(raw_data) is None
