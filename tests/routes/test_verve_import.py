"""File-based acceptance tests for Verve import and reprocessing."""

import json
from collections.abc import Callable, Generator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from geoalchemy2.shape import to_shape
from mypy_boto3_s3.client import S3Client
from pydantic import ValidationError
from sqlmodel import Session, col, select

from verve_backend.core.config import settings
from verve_backend.core.elevation import get_elevation_converter
from verve_backend.models import (
    Activity,
    RawTrackData,
    SegmentCut,
    SegmentSet,
    TrackPoint,
)
from verve_backend.schema.verve_file import VerveFeature

pytestmark = pytest.mark.usefixtures("celery_eager", "source_keys")

VALID_FILES = [
    "elevation_grid_node.json",
    "spatial_supplied_stats.json",
    "spatial_missing_stats.json",
    "spatial_partial_stats.json",
    "nonspatial_supplied_stats.json",
    "nonspatial_missing_stats.json",
    "summary_only_supplied_stats.json",
    "summary_only_missing_stats.json",
]
INVALID_FILES = [
    "invalid_swimming_version.json",
    "invalid_swimming_index.json",
    "invalid_mixed_geometry.json",
    "invalid_sensor_alignment.json",
    "unsupported_fractional_power.json",
]
UPLOAD_PATHS = ["/activity/import/", "/activity/auto/"]
EXPECTED_STATISTICS = {
    "elevation_grid_node.json": {
        "avg_speed": 36,
        "max_speed": 43.2,
        "avg_heartrate": None,
        "max_heartrate": None,
        "avg_power": None,
        "max_power": None,
    },
    "spatial_supplied_stats.json": {
        "avg_speed": 36,
        "max_speed": 43.2,
        "avg_heartrate": 90,
        "max_heartrate": 110,
        "avg_power": 200,
        "max_power": 250,
    },
    "spatial_missing_stats.json": {
        "avg_heartrate": 100,
        "max_heartrate": 100,
        "avg_power": 150,
        "max_power": 150,
    },
    "spatial_partial_stats.json": {
        "avg_speed": 36,
        "max_speed": None,
        "avg_heartrate": None,
        "max_heartrate": None,
        "avg_power": 150,
        "max_power": 150,
    },
    "nonspatial_supplied_stats.json": {
        "avg_speed": 0,
        "max_speed": 0,
        "avg_heartrate": 0,
        "max_heartrate": 0,
        "avg_power": 0,
        "max_power": 0,
    },
    "nonspatial_missing_stats.json": {
        "avg_speed": None,
        "max_speed": None,
        "avg_heartrate": 100,
        "max_heartrate": 100,
        "avg_power": 150,
        "max_power": 150,
    },
    "summary_only_supplied_stats.json": {
        "avg_speed": 36,
        "max_speed": 43.2,
        "avg_heartrate": 100,
        "max_heartrate": 120,
        "avg_power": 150,
        "max_power": 180,
    },
    "summary_only_missing_stats.json": {
        "avg_speed": None,
        "max_speed": None,
        "avg_heartrate": None,
        "max_heartrate": None,
        "avg_power": None,
        "max_power": None,
    },
}


def read_source(file_name: str) -> tuple[bytes, dict[str, Any]]:
    content = (
        resources.files("tests.resources")
        .joinpath("verve_import", file_name)
        .read_bytes()
    )
    return content, json.loads(content)


@pytest.mark.parametrize(
    "file_name", ["swimming_fractional_details.json", "swimming_summary_only.json"]
)
@pytest.mark.parametrize("upload_path", UPLOAD_PATHS)
def test_swimming_import_preserves_metadata_and_reprocessing(
    db: Session,
    upload_client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    object_store: S3Client,
    file_name: str,
    upload_path: str,
) -> None:
    from verve_backend.schema.exporter import _cast, _metadata_for_verve_export
    from verve_backend.schema.meta_data import SwimmingMetaDataEnvelopeV1
    from verve_backend.tasks import reprocess_stored_track

    content, source = read_source(file_name)
    response = upload_client.post(
        upload_path,
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (file_name, content, "application/json")},
    )
    assert response.status_code == 200, response.text
    activity_id = UUID(response.json()["id"])
    db.expire_all()
    activity = db.get(Activity, activity_id)
    assert activity is not None
    expected = (
        SwimmingMetaDataEnvelopeV1.model_validate(source["properties"]["metadata"])
        .to_core_meta_data(ZoneInfo(activity.timezone))
        .model_dump(mode="json")
    )
    assert activity.meta_data == expected
    assert activity.meta_data["pool_length_meters"] == pytest.approx(22.86)
    if file_name == "swimming_summary_only.json":
        assert activity.meta_data["lap_count"] == 8
        assert activity.meta_data["total_stroke_count"] == 0
        assert activity.meta_data["laps"] is None
    else:
        assert activity.meta_data["laps"][0]["distance_meters"] == pytest.approx(22.86)
        assert activity.meta_data["sets"][0]["durations"] == "PT1M55S"
        assert activity.meta_data["sets"][0]["avg_swofl"] == 73.5
        assert datetime.fromisoformat(
            activity.meta_data["laps"][0]["start_time"]
        ) == datetime(2026, 10, 13, 8, tzinfo=UTC)
        exported = VerveFeature.model_validate_json(_cast(db, activity.id).to_json())
        assert isinstance(exported.properties.metadata, SwimmingMetaDataEnvelopeV1)
        assert exported.properties.metadata.data.sets is not None
        assert exported.properties.metadata.data.sets[0].duration_seconds == 115
    converted = _metadata_for_verve_export(activity.meta_data)
    assert isinstance(converted, SwimmingMetaDataEnvelopeV1)
    assert (
        converted.to_core_meta_data(ZoneInfo("UTC")).model_dump(mode="json") == expected
    )
    for _ in range(2):
        result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
        assert result["error"] is None, result
        db.expire_all()
        db.refresh(activity)
        assert activity.meta_data == expected
        assert_source_bytes(db, object_store, activity, file_name)


@pytest.fixture
def upload_client(client: TestClient) -> Generator[TestClient]:
    # The session client already started the app; do not restart its lifespan.
    api = TestClient(
        client.app,
        base_url=str(client.base_url),
        raise_server_exceptions=False,
    )
    try:
        yield api
    finally:
        api.close()


@pytest.fixture
def source_keys(
    object_store: S3Client, temp_user_id: UUID
) -> Generator[Callable[[], set[str]]]:
    def keys() -> set[str]:
        pages = object_store.get_paginator("list_objects_v2").paginate(
            Bucket=settings.BOTO3_BUCKET, Prefix="tracks/"
        )
        return {item["Key"] for page in pages for item in page.get("Contents", [])}

    original_keys = keys()
    try:
        yield keys
    finally:
        # Also remove orphaned objects left by an upload that fails mid-request.
        for key in keys() - original_keys:
            metadata = object_store.head_object(
                Bucket=settings.BOTO3_BUCKET, Key=key
            ).get("Metadata", {})
            if metadata.get("uploaded_by") == str(temp_user_id):
                object_store.delete_object(Bucket=settings.BOTO3_BUCKET, Key=key)


@pytest.fixture
def activity_without_track(db: Session, temp_user_id: UUID) -> Activity:
    activity = Activity(
        user_id=temp_user_id,
        timezone="America/Los_Angeles",
        name="Existing activity name",
        type_id=1,
        sub_type_id=None,
        start=datetime(2024, 1, 1, tzinfo=UTC),
        duration=timedelta(hours=1),
        distance=999,
        moving_duration=timedelta(minutes=30),
        energy=999,
        elevation_change_up=999,
        elevation_change_down=999,
        avg_speed=999,
        max_speed=999,
        avg_heartrate=199,
        max_heartrate=199,
        avg_power=999,
        max_power=999,
        meta_data={"note": "Keep existing metadata"},
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@pytest.fixture
def stored_verve_file(
    db: Session,
    temp_user_id: UUID,
    activity_without_track: Activity,
    object_store: S3Client,
) -> Callable[[str], Activity]:
    def store(file_name: str) -> Activity:
        content, _ = read_source(file_name)
        activity = activity_without_track
        path = f"tracks/{uuid4()}"
        object_store.put_object(
            Bucket=settings.BOTO3_BUCKET,
            Key=path,
            Body=content,
            Metadata={
                "original_filename": file_name,
                "file_type": "json",
                "activity_id": str(activity.id),
                "uploaded_by": str(temp_user_id),
            },
        )
        db.add(
            RawTrackData(activity_id=activity.id, user_id=temp_user_id, store_path=path)
        )
        # Existing data makes failed reprocessing's rollback observable.
        db.add(
            TrackPoint(
                id=0,
                activity_id=activity.id,
                user_id=temp_user_id,
                segment_id=0,
                time=datetime(2024, 1, 1, tzinfo=UTC),
                heartrate=99,
                extensions={"original": 1},
            )
        )
        db.commit()
        return activity

    return store


def assert_statistics(activity: Activity, file_name: str) -> None:
    for field, expected in EXPECTED_STATISTICS[file_name].items():
        actual = getattr(activity, field)
        if expected is None:
            assert actual is None, field
        else:
            assert actual == pytest.approx(expected), field

    if file_name == "spatial_missing_stats.json":
        # Each 0.001-degree longitude step at 48 N is about 74 m.
        # Thirty-second steps and the sixty-second segment gap imply km/h,
        # rather than m/s; do not pin the parser's incidental rounding.
        assert activity.avg_speed is not None
        assert activity.max_speed is not None
        assert 7 < activity.avg_speed <= activity.max_speed
        assert 8.8 < activity.max_speed < 9.1


def assert_samples(db: Session, activity: Activity, source: dict[str, Any]) -> None:
    points = db.exec(
        select(TrackPoint)
        .where(TrackPoint.activity_id == activity.id)
        .order_by(col(TrackPoint.id))
    ).all()
    features = source["features"]
    assert len(points) == sum(
        len(feature["properties"]["coordTimes"]) for feature in features
    )
    expected_segments = [
        index
        for index, feature in enumerate(
            feature for feature in features if feature["properties"]["coordTimes"]
        )
        for _ in feature["properties"]["coordTimes"]
    ]
    assert [point.segment_id for point in points] == expected_segments
    assert [point.time for point in points] == [
        datetime.fromisoformat(value)
        for feature in features
        for value in feature["properties"]["coordTimes"]
    ]
    for attribute, member in [
        ("heartrate", "heartRates"),
        ("cadence", "cadences"),
        ("power", "powers"),
    ]:
        assert [getattr(point, attribute) for point in points] == [
            value
            for feature in features
            for value in feature["properties"].get(member, [])
        ], member
    assert [point.extensions.get("temperature") for point in points] == [
        value
        for feature in features
        for value in feature["properties"].get(
            "temperatures", [None] * len(feature["properties"]["coordTimes"])
        )
    ]

    expected_coordinates = [
        coordinate
        for feature in features
        if feature["geometry"] is not None
        for coordinate in feature["geometry"]["coordinates"]
    ]
    if expected_coordinates:
        assert len(points) == len(expected_coordinates)
        converter = get_elevation_converter()
        for point, (longitude, latitude, height) in zip(
            points, expected_coordinates, strict=True
        ):
            assert point.geography is not None
            assert point.geometry is not None
            location = to_shape(point.geography)
            assert location.x == pytest.approx(longitude)
            assert location.y == pytest.approx(latitude)
            assert point.elevation == pytest.approx(
                converter.to_sea_level(longitude, latitude, height)
            )
    else:
        assert all(
            point.geography is None and point.geometry is None for point in points
        )

    cuts = db.exec(
        select(SegmentCut.point_id)
        .join(SegmentSet, col(SegmentSet.id) == SegmentCut.set_id)
        .where(SegmentSet.activity_id == activity.id)
        .order_by(col(SegmentCut.point_id))
    ).all()
    assert list(cuts) == ([2] if len(points) == 6 else [])


def assert_activity(db: Session, activity: Activity, file_name: str) -> None:
    _, source = read_source(file_name)
    assert_samples(db, activity, source)
    assert_statistics(activity, file_name)
    assert activity.start == datetime(2026, 10, 17, 8, tzinfo=UTC)
    assert activity.duration == timedelta(seconds=180)
    assert activity.timezone == "UTC"

    props = source["properties"]
    distance = props.get("totalDistanceMeters")
    if distance is None:
        assert activity.distance is None
    else:
        assert activity.distance == pytest.approx(distance / 1000)
    assert activity.energy == props.get("totalEnergyKcal")

    moving_seconds = props.get("movingDurationSeconds")
    if moving_seconds is None and file_name in {
        "spatial_missing_stats.json",
        "spatial_partial_stats.json",
    }:
        moving_seconds = 180
    assert activity.moving_duration == (
        None if moving_seconds is None else timedelta(seconds=moving_seconds)
    )

    for field, member in [
        ("elevation_change_up", "elevationGain"),
        ("elevation_change_down", "elevationLoss"),
    ]:
        value = getattr(activity, field)
        if member in props:
            assert value == props[member], field
        elif source["features"][0]["geometry"] is not None:
            # Missing summaries are calculated from the converted track.
            assert value is not None, field
            assert value >= 0, field
        else:
            assert value is None, field


def assert_source_bytes(
    db: Session, object_store: S3Client, activity: Activity, file_name: str
) -> None:
    raw = db.get(RawTrackData, activity.id)
    assert raw is not None
    content, _ = read_source(file_name)
    response = object_store.get_object(Bucket=settings.BOTO3_BUCKET, Key=raw.store_path)
    with closing(response["Body"]) as body:
        assert body.read() == content


def database_snapshot(db: Session, user_id: UUID) -> dict[str, list[dict]]:
    db.expire_all()
    return {
        model.__name__: sorted(
            (
                row.model_dump()
                for row in db.exec(select(model).where(model.user_id == user_id)).all()
            ),
            key=repr,
        )
        for model in (Activity, RawTrackData, TrackPoint, SegmentSet, SegmentCut)
    }


@pytest.mark.parametrize("file_name", VALID_FILES)
@pytest.mark.parametrize("upload_path", UPLOAD_PATHS)
def test_verve_file_upload_preserves_samples_and_applies_statistics(
    db: Session,
    upload_client: TestClient,
    temp_user_token: str,
    object_store: S3Client,
    file_name: str,
    upload_path: str,
) -> None:
    content, source = read_source(file_name)
    response = upload_client.post(
        upload_path,
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (file_name, content, "application/json")},
    )
    assert response.status_code == 200, response.text
    activity_id = UUID(response.json()["id"])
    db.expire_all()
    activity = db.get(Activity, activity_id)
    assert activity is not None
    assert_activity(db, activity, file_name)
    assert_source_bytes(db, object_store, activity, file_name)
    assert activity.name == source["properties"]["name"]


@pytest.mark.parametrize("file_name", VALID_FILES)
def test_verve_file_reprocessing_is_repeatable_and_preserves_supplied_statistics(
    db: Session,
    temp_user_id: UUID,
    object_store: S3Client,
    stored_verve_file: Callable[[str], Activity],
    file_name: str,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    activity = stored_verve_file(file_name)
    _, source = read_source(file_name)
    expected_points = sum(
        len(feature["properties"]["coordTimes"]) for feature in source["features"]
    )
    raw = db.get(RawTrackData, activity.id)
    assert raw is not None
    original_path = raw.store_path

    for _ in range(2):
        result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
        assert result["error"] is None, result
        assert result["number_of_points"] == expected_points
        db.expire_all()
        db.refresh(activity)
        assert_activity(db, activity, file_name)
        assert activity.name == "Existing activity name"
        assert activity.type_id == 1
        assert activity.meta_data == {"note": "Keep existing metadata"}
        assert_source_bytes(db, object_store, activity, file_name)
        raw = db.get(RawTrackData, activity.id)
        assert raw is not None
        assert raw.store_path == original_path


@pytest.mark.parametrize("upload_path", UPLOAD_PATHS)
def test_verve_import_and_reprocessing_preserve_coerced_properties(
    db: Session,
    upload_client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    object_store: S3Client,
    upload_path: str,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    file_name = "nonspatial_coerced_properties.json"
    content, source = read_source(file_name)
    response = upload_client.post(
        upload_path,
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (file_name, content, "application/json")},
    )
    assert response.status_code == 200, response.text
    activity_id = UUID(response.json()["id"])

    for attempt in range(3):
        if attempt:
            result = reprocess_stored_track(
                activity_id=activity_id, user_id=temp_user_id
            )
            assert result["error"] is None, result
            assert result["number_of_points"] == 6
        db.expire_all()
        activity = db.get(Activity, activity_id)
        assert activity is not None
        assert_samples(db, activity, source)
        assert activity.start == datetime(2026, 10, 17, 7, 59, 30, tzinfo=UTC)
        assert activity.duration == timedelta(seconds=240)
        assert activity.distance == pytest.approx(1.234)
        assert activity.moving_duration == timedelta(0)
        assert activity.energy == 42
        assert activity.elevation_change_up == 0
        assert activity.elevation_change_down == 0
        assert activity.avg_speed == pytest.approx(36)
        assert activity.max_speed == pytest.approx(43.2)
        assert activity.avg_heartrate == 90
        assert activity.max_heartrate == 110
        assert activity.avg_power == 200
        assert activity.max_power == 250
        assert_source_bytes(db, object_store, activity, file_name)


@pytest.mark.parametrize("file_name", INVALID_FILES)
@pytest.mark.parametrize("upload_path", UPLOAD_PATHS)
def test_invalid_verve_file_is_rejected_before_writes(
    db: Session,
    upload_client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    source_keys: Callable[[], set[str]],
    file_name: str,
    upload_path: str,
) -> None:
    content, _ = read_source(file_name)
    original_database = database_snapshot(db, temp_user_id)
    original_objects = source_keys()
    response = upload_client.post(
        upload_path,
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (file_name, content, "application/json")},
    )
    assert {
        "status": response.status_code,
        "database": database_snapshot(db, temp_user_id),
        "new_objects": source_keys() - original_objects,
    } == {
        "status": 422,
        "database": original_database,
        "new_objects": set(),
    }, response.text


@pytest.mark.parametrize("file_name", INVALID_FILES)
def test_invalid_stored_verve_file_does_not_change_existing_activity(
    db: Session,
    temp_user_id: UUID,
    object_store: S3Client,
    stored_verve_file: Callable[[str], Activity],
    source_keys: Callable[[], set[str]],
    file_name: str,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    activity = stored_verve_file(file_name)
    original_database = database_snapshot(db, temp_user_id)
    original_objects = source_keys()
    result = reprocess_stored_track(activity_id=activity.id, user_id=temp_user_id)
    assert result["error"] is not None
    assert database_snapshot(db, temp_user_id) == original_database
    assert source_keys() == original_objects
    assert_source_bytes(db, object_store, activity, file_name)


@pytest.mark.parametrize("file_name", INVALID_FILES)
def test_invalid_verve_file_is_rejected_by_schema(file_name: str) -> None:
    content, _ = read_source(file_name)
    with pytest.raises(ValidationError):
        VerveFeature.model_validate_json(content)
