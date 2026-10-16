from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, delete

from verve_backend.models import TrackPoint
from verve_backend.schema.exporter import _cast
from verve_backend.schema.importer import convert_verve_file_to_activity
from verve_backend.schema.verve_file import VerveFeature


@pytest.mark.parametrize(
    ("summary", "stored_avg", "stored_max"),
    [
        pytest.param({"avg": 10, "max": 12}, 36, 43.2, id="available-values"),
        pytest.param({"avg": 0, "max": 0}, 0, 0, id="reported-zero"),
        pytest.param({"avg": 10}, 36, None, id="missing-maximum"),
        pytest.param({"max": 12}, None, 43.2, id="missing-average"),
        pytest.param({"avg": None, "max": None}, None, None, id="null-values"),
        pytest.param({}, None, None, id="empty-summary"),
    ],
)
def test_speed_summary_round_trip_uses_m_s_in_files_and_km_h_in_storage(
    db: Session,
    user1_id: UUID,
    summary: dict,
    stored_avg: float | None,
    stored_max: float | None,
) -> None:
    source = VerveFeature.model_validate(
        {
            "type": "FeatureCollection",
            "properties": {
                "verveVersion": "1.0",
                "generator": "SpeedUnitTest",
                "name": "Speed unit round trip",
                "activityType": "Cycling",
                "startTime": "2026-10-13T08:00:00Z",
                "durationSeconds": 60,
                "movingDurationSeconds": 60,
                "elevationGain": 1,
                "stats": {"speed": summary, "heartRate": {}, "power": {}},
            },
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[11, 48, 520], [11.001, 48.001, 521]],
                    },
                    "properties": {
                        "coordTimes": [
                            "2026-10-13T08:00:00Z",
                            "2026-10-13T08:01:00Z",
                        ]
                    },
                }
            ],
        }
    )
    for _ in range(2):
        activity = convert_verve_file_to_activity(
            session=db, user_id=user1_id, data=source, timezone=ZoneInfo("UTC")
        )
        try:
            if stored_avg is None:
                assert activity.avg_speed is None
            else:
                assert activity.avg_speed == pytest.approx(stored_avg)
            if stored_max is None:
                assert activity.max_speed is None
            else:
                assert activity.max_speed == pytest.approx(stored_max)
            assert activity.start == datetime(2026, 10, 13, 8, tzinfo=UTC)
            source = _cast(db, activity.id)
            assert source.properties.stats.speed is not None
            for name in ("avg", "max"):
                expected = summary.get(name)
                actual = getattr(source.properties.stats.speed, name)
                if expected is None:
                    assert actual is None
                else:
                    assert actual == pytest.approx(expected)
        finally:
            db.exec(
                delete(TrackPoint).where(col(TrackPoint.activity_id) == activity.id)
            )
            db.delete(activity)
            db.commit()
