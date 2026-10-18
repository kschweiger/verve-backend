"""Cadence unit boundaries through real import, response, and export paths."""

import json
from contextlib import closing
from importlib import resources
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from geo_track_analyzer.utils.internal import get_extension_value
from mypy_boto3_s3.client import S3Client
from sqlmodel import Session, col, select

from verve_backend.api.common.track import parse_track
from verve_backend.core.config import settings
from verve_backend.models import (
    Activity,
    ActivityCollection,
    ActivitySubType,
    ActivityType,
    RawTrackData,
    SegmentSet,
    TrackPoint,
)
from verve_backend.schema.exporter import _cast
from verve_backend.schema.importer import convert_verve_file_to_activity
from verve_backend.schema.verve_file import VerveFeature


@pytest.fixture
def cadence_source() -> VerveFeature:
    return VerveFeature.model_validate_json(
        resources.files("tests.resources")
        .joinpath("verve_import/running_cadence.json")
        .read_bytes()
    )


def stored_cadences(db: Session, activity_id: UUID) -> list[float | None]:
    return list(
        db.exec(
            select(TrackPoint.cadence)
            .where(TrackPoint.activity_id == activity_id)
            .order_by(col(TrackPoint.id))
        ).all()
    )


@pytest.mark.parametrize("validated", [False, True], ids=["attachment", "validated"])
@pytest.mark.parametrize(
    ("activity_type", "subtype", "expected"),
    [
        pytest.param("Foot Sports", "Run", [85.5, None, 0, 90, 0, None], id="run"),
        pytest.param(
            "Foot Sports", "Trail Run", [85.5, None, 0, 90, 0, None], id="trail-run"
        ),
        pytest.param(
            "Foot Sports", "Treadmill", [85.5, None, 0, 90, 0, None], id="treadmill"
        ),
        pytest.param("Foot Sports", "Walk", [171, None, 0, 180, 0, None], id="walk"),
        pytest.param(
            "Foot Sports",
            None,
            [171, None, 0, 180, 0, None],
            id="unspecified-foot-sport",
        ),
        pytest.param("Cycling", "Road", [171, None, 0, 180, 0, None], id="cycling"),
        pytest.param(
            "Indoor Cardio", "Indoor Rowing", [171, None, 0, 180, 0, None], id="rowing"
        ),
    ],
)
def test_verve_parser_uses_source_sport_for_cadence(
    cadence_source: VerveFeature,
    validated: bool,
    activity_type: str,
    subtype: str | None,
    expected: list[float | None],
) -> None:
    cadence_source.properties.activity_type = activity_type
    cadence_source.properties.activity_sub_type = subtype
    original = cadence_source.to_json()
    parsed = parse_track(
        file_name="cadence.json",
        file_content=original.encode(),
        fallback_timezone=ZoneInfo("UTC"),
        verve_data=cadence_source if validated else None,
    )
    points = [
        point for segment in parsed.track.track.segments for point in segment.points
    ]
    actual = [
        next(
            (
                float(ext.text)
                for ext in point.extensions
                if ext.tag == "cadence" and ext.text is not None
            ),
            None,
        )
        for point in points
    ]
    assert actual == expected
    assert cadence_source.to_json() == original


@pytest.mark.parametrize("nonspatial", [False, True], ids=["spatial", "nonspatial"])
@pytest.mark.parametrize("upload_path", ["/activity/import/", "/activity/auto/"])
def test_running_cadence_import_and_reprocessing_use_original_steps(
    db: Session,
    client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    object_store: S3Client,
    celery_eager: None,
    cadence_source: VerveFeature,
    nonspatial: bool,
    upload_path: str,
) -> None:
    from verve_backend.tasks import reprocess_stored_track

    if nonspatial:
        for feature in cadence_source.features:
            feature.geometry = None
    original = cadence_source.to_json().encode()
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.post(
        upload_path,
        headers=headers,
        files={"file": ("cadence.json", original, "application/json")},
    )
    assert response.status_code == 200, response.text
    activity_id = UUID(response.json()["id"])
    raw = db.get(RawTrackData, activity_id)
    assert raw is not None
    try:
        for attempt in range(3):
            if attempt:
                result = reprocess_stored_track(
                    activity_id=activity_id, user_id=temp_user_id
                )
                assert result["error"] is None, result
            db.expire_all()
            assert stored_cadences(db, activity_id) == [85.5, None, 0, 90, 0, None]
            points = db.exec(
                select(TrackPoint)
                .where(TrackPoint.activity_id == activity_id)
                .order_by(col(TrackPoint.id))
            ).all()
            assert [p.segment_id for p in points] == [0, 0, 0, 1, 1, 1]
            response = client.get(f"/track/{activity_id}", headers=headers)
            assert response.status_code == 200, response.text
            assert [p["cadence"] for p in response.json()["data"]] == [
                171,
                None,
                0,
                180,
                0,
                None,
            ]
            source = object_store.get_object(
                Bucket=settings.BOTO3_BUCKET, Key=raw.store_path
            )
            with closing(source["Body"]) as body:
                assert body.read() == original
    finally:
        object_store.delete_object(Bucket=settings.BOTO3_BUCKET, Key=raw.store_path)


def test_import_override_does_not_change_source_cadence_units(
    db: Session, temp_user_id: UUID, cadence_source: VerveFeature
) -> None:
    cycling = db.exec(select(ActivityType).where(ActivityType.name == "Cycling")).one()
    activity = convert_verve_file_to_activity(
        session=db,
        user_id=temp_user_id,
        data=cadence_source,
        timezone=ZoneInfo("UTC"),
        overwrite_type_id=cycling.id,
    )
    assert stored_cadences(db, activity.id) == [85.5, None, 0, 90, 0, None]


@pytest.fixture
def raw_cadence_activity(
    db: Session, temp_user_id: UUID, cadence_source: VerveFeature
) -> Activity:
    activity = convert_verve_file_to_activity(
        session=db, user_id=temp_user_id, data=cadence_source, timezone=ZoneInfo("UTC")
    )
    points = db.exec(
        select(TrackPoint)
        .where(TrackPoint.activity_id == activity.id)
        .order_by(col(TrackPoint.id))
    ).all()
    for point, cadence in zip(points, [85, None, 0, 90, 0, None], strict=True):
        point.cadence = cadence
        db.add(point)
    db.commit()
    return activity


def test_responses_use_current_activity_sport_without_rewriting_cadence(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    raw_cadence_activity: Activity,
) -> None:
    activity = raw_cadence_activity
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    response = client.get(f"/track/{activity.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert [p["cadence"] for p in response.json()["data"]] == [
        170,
        None,
        0,
        180,
        0,
        None,
    ]

    segment_set = db.exec(
        select(SegmentSet).where(SegmentSet.activity_id == activity.id)
    ).one()
    response = client.get(f"/track/segments/set/{segment_set.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert [s["cadence"] for s in response.json()["segments"]] == [
        {"min": 0, "max": 170, "avg": 85},
        {"min": 0, "max": 180, "avg": 90},
    ]

    walk = db.exec(
        select(ActivitySubType).where(
            ActivitySubType.type_id == activity.type_id, ActivitySubType.name == "Walk"
        )
    ).one()
    activity.sub_type_id = walk.id
    db.add(activity)
    db.commit()
    response = client.get(f"/track/{activity.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert [p["cadence"] for p in response.json()["data"]] == [85, None, 0, 90, 0, None]
    response = client.get(f"/track/segments/set/{segment_set.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert [s["cadence"] for s in response.json()["segments"]] == [
        {"min": 0, "max": 85, "avg": 42.5},
        {"min": 0, "max": 90, "avg": 45},
    ]
    db.expire_all()
    assert stored_cadences(db, activity.id) == [85, None, 0, 90, 0, None]


def test_collection_cadence_is_converted_for_each_activity(
    db: Session,
    client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    raw_cadence_activity: Activity,
    cadence_source: VerveFeature,
) -> None:
    cadence_source.properties.activity_type = "Cycling"
    cadence_source.properties.activity_sub_type = "Road"
    for feature in cadence_source.features:
        feature.properties.cadences = [85, None, 0]
    cycling = convert_verve_file_to_activity(
        session=db, user_id=temp_user_id, data=cadence_source, timezone=ZoneInfo("UTC")
    )
    collection = ActivityCollection(
        name="Run and ride",
        user_id=temp_user_id,
        activities=[raw_cadence_activity, cycling],
    )
    db.add(collection)
    db.commit()
    response = client.get(
        f"/collection/{collection.id}/track",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200, response.text
    points = response.json()["data"]
    assert [
        p["cadence"] for p in points if p["activity_id"] == str(raw_cadence_activity.id)
    ] == [170, None, 0, 180, 0, None]
    assert [p["cadence"] for p in points if p["activity_id"] == str(cycling.id)] == [
        85,
        None,
        0,
        85,
        None,
        0,
    ]


def test_running_verve_round_trips_do_not_accumulate_conversions(
    db: Session, temp_user_id: UUID, cadence_source: VerveFeature
) -> None:
    for _ in range(2):
        activity = convert_verve_file_to_activity(
            session=db,
            user_id=temp_user_id,
            data=cadence_source,
            timezone=ZoneInfo("UTC"),
        )
        assert stored_cadences(db, activity.id) == [85.5, None, 0, 90, 0, None]
        exported = _cast(db, activity.id)
        assert [f.properties.cadences for f in exported.features] == [
            [171, None, 0],
            [180, 0, None],
        ]
        assert _cast(db, activity.id).to_json() == exported.to_json()
        assert stored_cadences(db, activity.id) == [85.5, None, 0, 90, 0, None]
        cadence_source = VerveFeature.model_validate_json(exported.to_json())


@pytest.mark.parametrize(
    "cadences", [[0, 0, 0], [None, None, None]], ids=["reported-zero", "unavailable"]
)
def test_export_distinguishes_zero_cadence_from_unavailable_series(
    db: Session,
    temp_user_id: UUID,
    cadence_source: VerveFeature,
    cadences: list[int | None],
) -> None:
    for feature in cadence_source.features:
        feature.properties.cadences = cadences
    activity = convert_verve_file_to_activity(
        session=db, user_id=temp_user_id, data=cadence_source, timezone=ZoneInfo("UTC")
    )
    exported = _cast(db, activity.id)
    expected = [0, 0, 0] if cadences[0] == 0 else None
    assert [f.properties.cadences for f in exported.features] == [expected, expected]


def test_verve_attachment_validates_source_metadata_before_parsing(
    cadence_source: VerveFeature,
) -> None:
    source = cadence_source.model_dump(mode="json", by_alias=True)
    source["properties"].pop("activityType")

    with pytest.raises(HTTPException) as exc:
        parse_track(
            file_name="invalid.json",
            file_content=json.dumps(source).encode(),
            fallback_timezone=ZoneInfo("UTC"),
        )
    assert exc.value.status_code == 422


def test_supported_gpx_cadence_keeps_cycle_based_values() -> None:
    source = (
        b'<gpx version="1.1" creator="test"><trk><trkseg>'
        b'<trkpt lat="48" lon="11"><time>2026-10-18T10:00:00Z</time>'
        b"<extensions><cadence>85.5</cadence></extensions></trkpt>"
        b'<trkpt lat="48.001" lon="11.001"><time>2026-10-18T10:01:00Z</time>'
        b"<extensions><cadence>0</cadence></extensions></trkpt>"
        b"</trkseg></trk></gpx>"
    )
    parsed = parse_track(
        file_name="cadence.gpx", file_content=source, fallback_timezone=ZoneInfo("UTC")
    )
    assert [
        float(get_extension_value(p, "cadence"))
        for p in parsed.track.track.segments[0].points
    ] == [85.5, 0]


def test_fit_cadence_keeps_cycle_based_values() -> None:
    parsed = parse_track(
        file_name="cadence.fit",
        file_content=resources.files("tests.resources")
        .joinpath("MyWhoosh_1.fit")
        .read_bytes(),
        fallback_timezone=ZoneInfo("UTC"),
    )
    values = [
        float(extension.text)
        for segment in parsed.track.track.segments
        for point in segment.points
        for extension in point.extensions
        if extension.tag == "cadence" and extension.text is not None
    ]
    assert values[:3] == [0, 9, 18]


def test_fractional_cadence_is_rounded_only_for_verve_export(
    db: Session,
    client: TestClient,
    temp_user_id: UUID,
    temp_user_token: str,
    cadence_source: VerveFeature,
) -> None:
    cadence_source.properties.activity_type = "Cycling"
    cadence_source.properties.activity_sub_type = "Road"
    activity = convert_verve_file_to_activity(
        session=db, user_id=temp_user_id, data=cadence_source, timezone=ZoneInfo("UTC")
    )
    points = db.exec(
        select(TrackPoint)
        .where(TrackPoint.activity_id == activity.id)
        .order_by(col(TrackPoint.id))
    ).all()
    for point, value in zip(points, [85.5, 86.5, 0, 90, 0, None], strict=True):
        point.cadence = value
        db.add(point)
    db.commit()

    exported = _cast(db, activity.id)
    assert [f.properties.cadences for f in exported.features] == [
        [86, 86, 0],
        [90, 0, None],
    ]
    response = client.get(
        f"/track/{activity.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200, response.text
    assert [p["cadence"] for p in response.json()["data"]] == [
        85.5,
        86.5,
        0,
        90,
        0,
        None,
    ]
