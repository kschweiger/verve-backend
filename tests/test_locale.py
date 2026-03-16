from datetime import datetime

import pytest

from verve_backend.api.common.locale import (
    TimeOfDay,
    get_activity_name,
    get_tag_name,
    get_time_of_day,
)


@pytest.mark.parametrize(
    ("ts", "exp"),
    [
        (datetime(2024, 1, 1, 10), TimeOfDay.MORNING),
        (datetime(2024, 1, 1, 14), TimeOfDay.AFTERNOON),
        (datetime(2024, 1, 1, 20), TimeOfDay.EVENING),
        (datetime(2024, 1, 1, 3), TimeOfDay.NIGHT),
    ],
)
def test_get_time_of_day(ts: datetime, exp: TimeOfDay) -> None:
    assert get_time_of_day(ts) == exp


@pytest.mark.parametrize(
    ("act", "ts", "locale", "exp"),
    [
        ("cycling", datetime(2024, 1, 1, 10), "en", "Morning Ride"),
        ("cycling", datetime(2024, 1, 1, 10), "de", "Fahrt am Morgen"),
        ("blubb", datetime(2024, 1, 1, 10), "de", "Aktivität am Morgen"),
    ],
)
def test_get_activity_name(act: str, ts: datetime, locale: str, exp: str) -> None:
    assert exp == get_activity_name(act, ts, locale)


@pytest.mark.parametrize(
    ("name", "locale", "data_type", "exp"),
    [
        ("Interval", "en", "tag", "Interval"),
        ("Interval", "de", "tag", "Intervall"),
        ("Interval", "fr", "tag", "Interval"),
        ("Workout", "en", "tag_category", "Workout"),
        ("Workout", "de", "tag_category", "Training"),
        ("Workout", "fr", "tag_category", "Workout"),
    ],
)
def test_get_tag_name(name: str, locale: str, data_type: str, exp: str) -> None:
    assert exp == get_tag_name(
        name,
        locale,
        data_type,  # type: ignore
    )
