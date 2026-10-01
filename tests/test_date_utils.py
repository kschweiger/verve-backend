from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from verve_backend.core.date_utils import get_local_date_range_utc_bounds


@pytest.mark.parametrize(
    ("day", "expected_start", "expected_end", "expected_duration"),
    [
        (
            date(2025, 3, 30),
            datetime(2025, 3, 29, 23, tzinfo=UTC),
            datetime(2025, 3, 30, 22, tzinfo=UTC),
            timedelta(hours=23),
        ),
        (
            date(2025, 10, 26),
            datetime(2025, 10, 25, 22, tzinfo=UTC),
            datetime(2025, 10, 26, 23, tzinfo=UTC),
            timedelta(hours=25),
        ),
    ],
)
def test_berlin_local_day_bounds_follow_daylight_saving(
    day: date,
    expected_start: datetime,
    expected_end: datetime,
    expected_duration: timedelta,
) -> None:
    start, end = get_local_date_range_utc_bounds(
        day, day + timedelta(days=1), ZoneInfo("Europe/Berlin")
    )

    assert (start, end) == (expected_start, expected_end)
    assert end - start == expected_duration
