from typing import Any

import pytest

from verve_backend.core.meta_data import (
    ActivityMetaData,
    LapData,
    SwimmingMetaData,
    SwimStyle,
    parse_meta_data,
)


def test_activity_meta_data_target() -> None:
    ActivityMetaData(target="ActivityMetaData")

    with pytest.raises(ValueError):  # noqa: PT011
        ActivityMetaData(target="WrongTarget")


@pytest.mark.parametrize(
    "initial_data",
    [
        SwimmingMetaData(
            segments=[LapData(count=5, lap_lenths=50, style=SwimStyle.FREESTYLE)]
        ),
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
        # Missing target
        {"segments": [{"count": 10}]},
        # Missing required value
        {"target": "SwimmingMetaData", "segments": [{"style": "freestyle"}]},
        # Invaild enum type
        {"target": "SwimmingMetaData", "segments": [{"count": 2, "style": "doggy"}]},
    ],
)
def test_parse_meta_data_invalid(raw_data: dict[str, Any]) -> None:
    assert parse_meta_data(raw_data) is None
