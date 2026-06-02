from datetime import datetime, timedelta
from typing import Any

import pytest

from verve_backend.core.meta_data import (
    ActivityMetaData,
    LapData,
    SetData,
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
            pool_length_meters=50,
            lap_count=2,
            set_count=1,
            sets=[
                SetData(
                    index=0,
                    start_time=datetime(year=2025, month=1, day=2, hour=13, minute=10),
                    end_time=datetime(
                        year=2025, month=1, day=2, hour=13, minute=12, second=30
                    ),
                    durations=timedelta(minutes=2),
                    distance_meters=100,
                    style=SwimStyle.FREESTYLE,
                    lap_start_index=0,
                    lap_end_index=1,
                    lap_count=2,
                    avg_swofl=30.0,
                )
            ],
            laps=[
                LapData(
                    index=0,
                    start_time=datetime(year=2025, month=1, day=2, hour=13, minute=10),
                    end_time=datetime(year=2025, month=1, day=2, hour=13, minute=11),
                    durations=timedelta(minutes=1),
                    distance_meters=50,
                    style=SwimStyle.FREESTYLE,
                    swolf=30.0,
                    rest_after=timedelta(seconds=30),
                ),
                LapData(
                    index=1,
                    start_time=datetime(
                        year=2025, month=1, day=2, hour=13, minute=11, second=30
                    ),
                    end_time=datetime(
                        year=2025, month=1, day=2, hour=13, minute=12, second=30
                    ),
                    durations=timedelta(minutes=1),
                    distance_meters=50,
                    style=SwimStyle.FREESTYLE,
                    swolf=30.0,
                ),
            ],
        )
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
        {
            "pool_length_meters": 50,
            "sets": [{"index": 0, "style": "freestyle"}],
            "laps": [{"index": 0, "style": "freestyle"}],
        },
        # No required filed set
        {
            "target": "SwimmingMetaData",
        },
        # Required index in sets missing
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "lap_count": 1,
            "set_count": 1,
            "sets": [{"style": "freestyle"}],
            "laps": [{"index": 0, "style": "freestyle"}],
        },
        # Required index in laps missing
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "lap_count": 1,
            "set_count": 1,
            "sets": [{"index": 0, "style": "freestyle"}],
            "laps": [{"style": "freestyle"}],
        },
        # lap count missing with set laps
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "laps": [{"index": 0, "style": "freestyle"}],
        },
        # lap count set but laps missing
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "lap_count": 1,
        },
        # set count missing with set sets
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "sets": [{"index": 0, "style": "freestyle"}],
        },
        # set count set but sets missing
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "set_count": 1,
        },
        # Invaild enum type
        {
            "target": "SwimmingMetaData",
            "pool_length_meters": 50,
            "sets": [{"index": 0, "style": "doggy"}],
            "laps": [{"index": 0, "style": "freestyle"}],
        },
    ],
)
def test_parse_meta_data_invalid(raw_data: dict[str, Any]) -> None:
    assert parse_meta_data(raw_data) is None
