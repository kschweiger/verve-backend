import json
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from importlib import resources
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from mypy_boto3_s3.client import S3Client
from pytest_mock import MockerFixture
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, text
from structlog.testing import capture_logs

from verve_backend.core.config import settings
from verve_backend.models import (
    Activity,
    ActivityHighlight,
    Goal,
    HighlightMetric,
    HighlightTimeScope,
    RawTrackData,
    SegmentCut,
    SegmentSet,
    TrackPoint,
    UserSettings,
)


@pytest.fixture
def stored_track(
    db: Session, temp_user_id: UUID, object_store: S3Client
) -> Generator[Callable[[str, bytes], Activity]]:
    paths = []

    def store(file_name: str, content: bytes) -> Activity:
        activity = Activity(
            user_id=temp_user_id,
            timezone="America/Los_Angeles",
            name="Edited activity name",
            type_id=1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            duration=timedelta(hours=99),
            distance=999,
            avg_power=999,
            max_power=999,
            meta_data={"note": "Keep my edits"},
            sub_type_id=None,
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        path = f"tracks/{uuid4()}"
        object_store.put_object(
            Bucket=settings.BOTO3_BUCKET,
            Key=path,
            Body=content,
            Metadata={
                "original_filename": file_name,
                "file_type": file_name.rsplit(".", 1)[-1].lower(),
                "activity_id": str(activity.id),
                "uploaded_by": str(temp_user_id),
            },
        )
        paths.append(path)
        db.add(
            RawTrackData(activity_id=activity.id, user_id=temp_user_id, store_path=path)
        )
        db.add(
            TrackPoint(
                id=0,
                activity_id=activity.id,
                user_id=temp_user_id,
                segment_id=0,
                time=activity.start,
                extensions={"distance": 1, "enhanced_speed": 1},
            )
        )
        db.commit()
        return activity

    try:
        yield store
    finally:
        for path in paths:
            object_store.delete_object(Bucket=settings.BOTO3_BUCKET, Key=path)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/admin/reprocess_tracks"),
        ("POST", f"/admin/reprocess_track?activity_id={UUID(int=1)}"),
        ("POST", "/admin/recalculate_highlights"),
        ("GET", f"/admin/tasks/{UUID(int=1)}"),
    ],
)
def test_admin_jobs_require_admin(
    client: TestClient, user1_token: str, method: str, path: str
) -> None:
    response = client.request(
        method, path, headers={"Authorization": f"Bearer {user1_token}"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/admin/reprocess_tracks"),
        ("POST", f"/admin/reprocess_track?activity_id={UUID(int=1)}"),
        ("POST", "/admin/recalculate_highlights"),
        ("GET", f"/admin/tasks/{UUID(int=1)}"),
    ],
)
def test_admin_jobs_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 401


def test_reprocess_fit_rebuilds_renamed_extensions_and_raw_segments(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    object_store: S3Client,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    content = resources.files("tests.resources").joinpath("MyWhoosh_1.fit").read_bytes()
    activity = stored_track("MyWhoosh_1.fit", content)
    raw = db.get(RawTrackData, activity.id)
    assert raw is not None
    path = raw.store_path

    for _ in range(2):
        result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
        assert result["error"] is None
        assert result["number_of_points"] == 2070
        db.expire_all()
        points = db.exec(
            select(TrackPoint)
            .where(TrackPoint.activity_id == activity.id)
            .order_by(TrackPoint.id)
        ).all()
        assert len(points) == 2070
        assert points[0].time == datetime(2025, 2, 14, 18, 55, 57, tzinfo=UTC)
        assert {"raw_distance_m", "enhanced_speed_ms"} <= points[0].extensions.keys()
        assert "distance" not in points[0].extensions
        assert "enhanced_speed" not in points[0].extensions
        segment_sets = db.exec(
            select(SegmentSet).where(SegmentSet.activity_id == activity.id)
        ).all()
        assert len(segment_sets) == 1
        assert segment_sets[0].name == "Raw track segments"
        assert db.exec(
            select(SegmentCut.point_id).where(SegmentCut.set_id == segment_sets[0].id)
        ).all() == [599]

    assert db.get(RawTrackData, activity.id).store_path == path
    stored = object_store.get_object(Bucket=settings.BOTO3_BUCKET, Key=path)
    try:
        assert stored["Body"].read() == content
    finally:
        stored["Body"].close()


@pytest.mark.parametrize("set_name", ["My custom split", "Raw track segments"])
@pytest.mark.parametrize(
    ("cut_time", "expected_cut_ids"),
    [
        pytest.param(datetime(2026, 8, 10, 8, 5, tzinfo=UTC), [1], id="remap-cut"),
        pytest.param(datetime(2020, 1, 1, tzinfo=UTC), [], id="remove-unresolved-cut"),
    ],
)
def test_reprocess_keeps_new_data_and_resolves_custom_cuts(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    set_name: str,
    cut_time: datetime,
    expected_cut_ids: list[int],
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    content = (
        resources.files("tests.resources.timezones")
        .joinpath("berlin-summer-local.gpx")
        .read_bytes()
    )
    activity = stored_track("BERLIN.GPX", content)
    db.add(
        TrackPoint(
            id=10,
            activity_id=activity.id,
            user_id=temp_user_id,
            segment_id=0,
            time=cut_time,
        )
    )
    custom_set = SegmentSet(
        user_id=temp_user_id, activity_id=activity.id, name=set_name
    )
    db.add(custom_set)
    db.commit()
    db.refresh(custom_set)
    set_id = custom_set.id
    db.add(SegmentCut(user_id=temp_user_id, set_id=set_id, point_id=10))
    db.commit()

    result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
    assert result["error"] is None
    assert result["removed_cuts"] == (0 if expected_cut_ids else 1)
    db.refresh(activity)
    assert activity.timezone == "Europe/Berlin"
    assert activity.start == datetime(2026, 8, 10, 8, tzinfo=UTC)
    assert activity.duration == timedelta(minutes=10)
    assert activity.avg_power is None
    assert activity.max_power is None
    assert activity.name == "Edited activity name"
    assert activity.meta_data == {"note": "Keep my edits"}
    db.expire_all()
    assert (
        db.exec(select(SegmentCut.point_id).where(SegmentCut.set_id == set_id)).all()
        == expected_cut_ids
    )
    assert (db.get(SegmentSet, set_id) is not None) == bool(expected_cut_ids)


def test_reprocess_rolls_back_all_batches_on_database_failure(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    start = datetime(2026, 8, 10, 8, tzinfo=UTC)
    points = "".join(
        f'<trkpt lat="52.52" lon="13.405"><ele>35</ele>'
        f"<time>{(start + timedelta(seconds=i)).isoformat()}</time></trkpt>"
        for i in range(101)
    )
    activity = stored_track(
        "long.gpx", f"<gpx><trk><trkseg>{points}</trkseg></trk></gpx>".encode()
    )
    db.exec(
        text(
            "ALTER TABLE track_points ADD CONSTRAINT reprocessing_test_point_limit "
            f"CHECK (user_id != '{temp_user_id}'::uuid OR id < 100) NOT VALID"
        )
    )
    db.commit()
    try:
        result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
        assert result["error"] is not None
        db.refresh(activity)
        assert activity.distance == 999
        assert activity.timezone == "America/Los_Angeles"
        remaining = db.exec(
            select(TrackPoint).where(TrackPoint.activity_id == activity.id)
        ).all()
        assert len(remaining) == 1
        assert remaining[0].extensions == {"distance": 1, "enhanced_speed": 1}
    finally:
        db.exec(
            text(
                "ALTER TABLE track_points DROP CONSTRAINT reprocessing_test_point_limit"
            )
        )
        db.commit()


def test_admin_queues_each_track_and_reports_partial_failure(
    client: TestClient,
    admin_token: str,
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    celery_eager: None,
    mocker: MockerFixture,
) -> None:
    from verve_backend.celery_app import celery
    from verve_backend.enums import GoalAggregation, GoalType
    from verve_backend.tasks import finish_track_reprocessing, reprocess_stored_track

    mocker.patch.object(reprocess_stored_track, "store_eager_result", True)
    mocker.patch.object(finish_track_reprocessing, "store_eager_result", True)
    mocker.patch.dict(celery.conf.changes, {"task_store_eager_result": True})
    content = (
        resources.files("tests.resources.timezones")
        .joinpath("berlin-summer-local.gpx")
        .read_bytes()
    )
    good = stored_track("good.gpx", content)
    bad = stored_track("bad.gpx", b"This is not a GPX file")
    cached_goal = Goal(
        user_id=temp_user_id,
        name="Cached progress",
        target=100,
        current=99,
        current_updated=datetime(2026, 1, 1, tzinfo=UTC),
        type=GoalType.ACTIVITY,
        aggregation=GoalAggregation.COUNT,
    )
    manual_goal = Goal(
        user_id=temp_user_id,
        name="Manual progress",
        target=100,
        current=7,
        type=GoalType.MANUAL,
        aggregation=GoalAggregation.COUNT,
    )
    db.add_all([cached_goal, manual_goal])
    db.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/admin/reprocess_tracks",
        headers=headers,
        params={"user_id": str(temp_user_id)},
    )
    assert response.status_code == 202
    jobs = response.json()
    assert {job["activity_id"] for job in jobs["tracks"]} == {str(good.id), str(bad.id)}
    assert len(jobs["completion_tasks"]) == 1
    task_ids = [job["task_id"] for job in [*jobs["tracks"], *jobs["completion_tasks"]]]
    try:
        status = client.get(
            f"/admin/tasks/{jobs['completion_tasks'][0]['task_id']}", headers=headers
        )
        assert status.status_code == 200
        assert status.json()["state"] == "SUCCESS"
        report = status.json()["result"]
        assert report["reprocessed"] == 1
        assert report["failed"] == 1
        assert report["highlights_rebuilt"] is True
        assert {
            track["activity_id"] for track in report["tracks"] if track["error"]
        } == {str(bad.id)}
        db.refresh(bad)
        assert bad.distance == 999
        db.refresh(cached_goal)
        db.refresh(manual_goal)
        assert cached_goal.current == 0
        assert cached_goal.current_updated is None
        assert manual_goal.current == 7
        highlights = db.exec(
            select(ActivityHighlight).where(ActivityHighlight.user_id == temp_user_id)
        ).all()
        assert highlights
        identities = [(h.activity_id, h.metric, h.scope, h.year) for h in highlights]
        assert len(identities) == len(set(identities))
    finally:
        for task_id in task_ids:
            celery.AsyncResult(task_id).forget()


@pytest.mark.parametrize(
    "path", ["/admin/reprocess_tracks", "/admin/recalculate_highlights"]
)
def test_admin_recalculation_rejects_unknown_user(
    client: TestClient, admin_token: str, path: str
) -> None:
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"user_id": str(uuid4())},
    )
    assert response.status_code == 400


def test_admin_reprocesses_only_the_requested_activity(
    client: TestClient,
    admin_token: str,
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    celery_eager: None,
    mocker: MockerFixture,
) -> None:
    from verve_backend.celery_app import celery
    from verve_backend.tasks import finish_track_reprocessing, reprocess_stored_track

    mocker.patch.object(reprocess_stored_track, "store_eager_result", True)
    mocker.patch.object(finish_track_reprocessing, "store_eager_result", True)
    mocker.patch.dict(celery.conf.changes, {"task_store_eager_result": True})
    content = (
        resources.files("tests.resources.timezones")
        .joinpath("berlin-summer-local.gpx")
        .read_bytes()
    )
    selected = stored_track("selected.gpx", content)
    other = stored_track("other.gpx", content)
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/admin/reprocess_track",
        headers=headers,
        params={"activity_id": str(selected.id)},
    )
    assert response.status_code == 202
    jobs = response.json()
    assert len(jobs["tracks"]) == 1
    assert jobs["tracks"][0]["activity_id"] == str(selected.id)
    assert jobs["tracks"][0]["user_id"] == str(temp_user_id)
    assert len(jobs["completion_tasks"]) == 1
    try:
        status = client.get(
            f"/admin/tasks/{jobs['completion_tasks'][0]['task_id']}", headers=headers
        ).json()
        assert status["state"] == "SUCCESS"
        assert status["result"]["reprocessed"] == 1
        assert status["result"]["highlights_rebuilt"] is True
        db.refresh(selected)
        db.refresh(other)
        assert selected.duration == timedelta(minutes=10)
        assert other.duration == timedelta(hours=99)
    finally:
        for job in [*jobs["tracks"], *jobs["completion_tasks"]]:
            celery.AsyncResult(job["task_id"]).forget()


@pytest.mark.parametrize("has_activity", [False, True])
def test_admin_single_reprocessing_requires_activity_and_source(
    client: TestClient,
    admin_token: str,
    db: Session,
    temp_user_id: UUID,
    has_activity: bool,
) -> None:
    activity_id = uuid4()
    if has_activity:
        activity = Activity(
            id=activity_id,
            user_id=temp_user_id,
            timezone="Europe/Berlin",
            name="No stored source",
            type_id=1,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            duration=timedelta(hours=1),
            distance=12,
            sub_type_id=None,
        )
        db.add(activity)
        db.commit()
    response = client.post(
        "/admin/reprocess_track",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"activity_id": str(activity_id)},
    )
    assert response.status_code == 404


def test_missing_stored_file_logs_location_and_keeps_activity(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    object_store: S3Client,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    activity = stored_track("missing.gpx", b"Deleted original file")
    raw = db.get(RawTrackData, activity.id)
    assert raw is not None
    path = raw.store_path
    object_store.delete_object(Bucket=settings.BOTO3_BUCKET, Key=path)
    with capture_logs() as logs:
        result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)

    assert "not available" in result["error"]
    assert settings.BOTO3_BUCKET in result["error"]
    assert path in result["error"]
    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert any(
        entry.get("activity_id") == str(activity.id)
        and entry.get("bucket") == settings.BOTO3_BUCKET
        and entry.get("key") == path
        and "not available" in entry["event"]
        and not entry.get("exc_info")
        for entry in errors
    )
    db.refresh(activity)
    assert activity.distance == 999
    assert db.get(RawTrackData, activity.id) is not None
    points = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == activity.id)
    ).all()
    assert len(points) == 1


def test_admin_recalculates_highlights_without_stored_tracks(
    client: TestClient,
    admin_token: str,
    db: Session,
    temp_user_id: UUID,
    celery_eager: None,
    mocker: MockerFixture,
) -> None:
    from verve_backend.celery_app import celery
    from verve_backend.tasks import recalculate_user_highlights

    mocker.patch.object(recalculate_user_highlights, "store_eager_result", True)
    mocker.patch.dict(celery.conf.changes, {"task_store_eager_result": True})
    activity = Activity(
        user_id=temp_user_id,
        timezone="Europe/Berlin",
        name="Manual activity",
        type_id=1,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        duration=timedelta(hours=1),
        distance=12,
        sub_type_id=None,
    )
    db.add(activity)
    db.commit()
    db.add(
        ActivityHighlight(
            user_id=temp_user_id,
            activity_id=activity.id,
            type_id=1,
            metric=HighlightMetric.DISTANCE,
            scope=HighlightTimeScope.YEARLY,
            year=2026,
            rank=1,
            value=999,
        )
    )
    db.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}
    for _ in range(2):
        response = client.post(
            "/admin/recalculate_highlights",
            headers=headers,
            params={"user_id": str(temp_user_id)},
        )
        assert response.status_code == 202
        jobs = response.json()["users"]
        assert len(jobs) == 1
        assert jobs[0]["user_id"] == str(temp_user_id)
        task_id = jobs[0]["task_id"]
        try:
            status = client.get(f"/admin/tasks/{task_id}", headers=headers).json()
            assert status["state"] == "SUCCESS"
            assert status["result"]["highlights_rebuilt"] is True
            db.expire_all()
            highlights = db.exec(
                select(ActivityHighlight).where(
                    ActivityHighlight.user_id == temp_user_id,
                    ActivityHighlight.metric == HighlightMetric.DISTANCE,
                )
            ).all()
            assert len(highlights) == 2
            assert all(
                h.activity_id == activity.id and h.value == 12 for h in highlights
            )
            assert {h.scope for h in highlights} == {
                HighlightTimeScope.YEARLY,
                HighlightTimeScope.LIFETIME,
            }
            assert db.get(RawTrackData, activity.id) is None
        finally:
            celery.AsyncResult(task_id).forget()


@pytest.mark.parametrize(
    ("declared_zone", "expected_zone", "expected_start"),
    [
        pytest.param(
            None,
            "Europe/Berlin",
            datetime(2026, 8, 10, 7, tzinfo=UTC),
            id="user-timezone-fallback",
        ),
        pytest.param(
            "America/Los_Angeles",
            "America/Los_Angeles",
            datetime(2026, 8, 10, 16, tzinfo=UTC),
            id="declared-verve-timezone",
        ),
    ],
)
def test_reprocess_nonspatial_json_resolves_timezone(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
    declared_zone: str | None,
    expected_zone: str,
    expected_start: datetime,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    user_settings = db.get(UserSettings, temp_user_id)
    user_settings.timezone = "Europe/Berlin"
    db.add(user_settings)
    db.commit()
    data = json.loads(
        resources.files("tests.resources.timezones")
        .joinpath("verve-no-geometry-no-zone.json")
        .read_bytes()
    )
    if declared_zone is not None:
        data["properties"]["timezone"] = declared_zone
    activity = stored_track("nonspatial.json", json.dumps(data).encode())

    result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
    assert result["error"] is None
    assert result["number_of_points"] == 3
    db.refresh(activity)
    assert activity.timezone == expected_zone
    assert activity.start == expected_start
    assert activity.duration == timedelta(minutes=10)
    assert activity.distance is None
    points = db.exec(
        select(TrackPoint).where(TrackPoint.activity_id == activity.id)
    ).all()
    assert all(point.geography is None and point.geometry is None for point in points)


def test_failed_highlight_recalculation_preserves_previous_rankings(
    db: Session,
    temp_user_id: UUID,
    stored_track: Callable[[str, bytes], Activity],
) -> None:
    from verve_backend.tasks import recalculate_user_highlights

    activity = stored_track(
        "unused.gpx", b"Source is not needed for highlight rebuilds"
    )
    existing = ActivityHighlight(
        user_id=temp_user_id,
        activity_id=activity.id,
        type_id=1,
        metric=HighlightMetric.DISTANCE,
        scope=HighlightTimeScope.YEARLY,
        year=2024,
        rank=1,
        value=123,
    )
    db.add(existing)
    db.commit()
    highlight_id = existing.id
    db.exec(
        text(
            "ALTER TABLE activity_highlights ADD CONSTRAINT highlight_test_value_limit "
            f"CHECK (user_id != '{temp_user_id}'::uuid OR value != 999) NOT VALID"
        )
    )
    db.commit()
    try:
        with pytest.raises(IntegrityError):
            recalculate_user_highlights(user_id=temp_user_id)
        db.expire_all()
        remaining = db.exec(
            select(ActivityHighlight).where(ActivityHighlight.user_id == temp_user_id)
        ).all()
        assert len(remaining) == 1
        assert remaining[0].id == highlight_id
        assert remaining[0].value == 123
    finally:
        db.exec(
            text(
                "ALTER TABLE activity_highlights DROP CONSTRAINT "
                "highlight_test_value_limit"
            )
        )
        db.commit()
