from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from verve_backend.api.common.track import load_activity_track
from verve_backend.models import Activity, TrackPoint


@pytest.fixture
def activity(db: Session, user1_id: UUID):  # noqa: ANN201
    value = Activity(
        user_id=user1_id,
        name="Loader test",
        type_id=1,
        distance=None,
        sub_type_id=None,
        timezone="UTC",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        duration=timedelta(seconds=60),
    )
    db.add(value)
    db.commit()
    yield value
    for point in db.exec(select(TrackPoint).where(TrackPoint.activity_id == value.id)):
        db.delete(point)
    db.flush()
    db.delete(value)
    db.commit()


def test_load_preserves_segments_and_samples(db: Session, activity: Activity) -> None:
    for point_id, segment_id in [(3, 8), (1, 2), (0, 2)]:
        db.add(
            TrackPoint(
                id=point_id,
                activity_id=activity.id,
                user_id=activity.user_id,
                segment_id=segment_id,
                geography=f"SRID=4326;POINT({11 + point_id} 48)",
                elevation=None if point_id == 1 else 500 + point_id,
                time=None if point_id == 1 else activity.start,
                heartrate=0,
                cadence=85.5,
                power=0,
            )
        )
    db.commit()
    loaded = load_activity_track(db, activity.id)
    assert [len(segment.points) for segment in loaded.track.segments] == [2, 1]
    points = [p for segment in loaded.track.segments for p in segment.points]
    assert [(p.latitude, p.longitude) for p in points] == [(48, 11), (48, 12), (48, 14)]
    assert [p.elevation for p in points] == [500, None, 503]
    assert [p.time for p in points] == [activity.start, None, activity.start]
    assert {e.tag: e.text for e in points[0].extensions} == {
        "heartrate": "0",
        "cadence": "85.5",
        "power": "0",
    }


def test_nonspatial_track_is_rejected(db: Session, activity: Activity) -> None:
    db.add(
        TrackPoint(
            id=0,
            activity_id=activity.id,
            user_id=activity.user_id,
            segment_id=0,
        )
    )
    db.commit()
    with pytest.raises(ValueError, match="without coordinates"):
        load_activity_track(db, activity.id)


def test_missing_track_is_rejected(db: Session) -> None:
    with pytest.raises(ValueError, match="no points"):
        load_activity_track(db, uuid4())
