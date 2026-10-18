"""Integration coverage for Verve file elevation boundaries."""

import json
from importlib import resources
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, col, delete, select

from verve_backend.api.common.track import parse_track
from verve_backend.core.elevation import get_elevation_converter
from verve_backend.models import TrackPoint
from verve_backend.schema.exporter import _cast
from verve_backend.schema.importer import convert_verve_file_to_activity
from verve_backend.schema.verve_file import VerveFeature


def test_non_verve_geojson_keeps_original_heights() -> None:
    source = json.loads(
        resources.files("tests.resources")
        .joinpath("verve_import/elevation_grid_node.json")
        .read_bytes()
    )
    source.pop("properties")
    parsed = parse_track(
        file_name="track.json",
        file_content=json.dumps(source).encode(),
        fallback_timezone=ZoneInfo("UTC"),
    )
    assert [
        p.elevation for segment in parsed.track.track.segments for p in segment.points
    ] == [
        p[2]
        for feature in source["features"]
        for p in feature["geometry"]["coordinates"]
    ]


def test_verve_import_export_round_trip(db: Session, user1_id: UUID) -> None:
    source = VerveFeature.model_validate_json(
        resources.files("tests.resources")
        .joinpath("verve_import/elevation_grid_node.json")
        .read_bytes()
    )
    original = source.model_copy(deep=True)
    converter = get_elevation_converter()
    expected_heights = [
        converter.to_sea_level(lon, lat, height)
        for feature in original.features
        if feature.geometry is not None
        for lon, lat, height in feature.geometry.coordinates
    ]
    for _ in range(2):
        activity = convert_verve_file_to_activity(
            session=db, user_id=user1_id, data=source, timezone=ZoneInfo("UTC")
        )
        try:
            points = db.exec(
                select(TrackPoint)
                .where(TrackPoint.activity_id == activity.id)
                .order_by(col(TrackPoint.id))
            ).all()
            assert [p.elevation for p in points] == pytest.approx(expected_heights)
            assert [p.segment_id for p in points] == [0, 0, 0, 1, 1, 1]
            assert activity.elevation_change_up == 0
            assert activity.elevation_change_down == 0
            exported = _cast(db, activity.id)
            for actual, expected in zip(
                exported.features, original.features, strict=True
            ):
                assert actual.geometry is not None
                assert expected.geometry is not None
                for position, original_position in zip(
                    actual.geometry.coordinates,
                    expected.geometry.coordinates,
                    strict=True,
                ):
                    assert position == pytest.approx(original_position, abs=1e-7)
                assert actual.properties == expected.properties
            assert _cast(db, activity.id).to_json() == exported.to_json()
            db.expire_all()
            assert [p.elevation for p in points] == pytest.approx(expected_heights)
            source = VerveFeature.model_validate_json(exported.to_json())
        finally:
            db.exec(
                delete(TrackPoint).where(col(TrackPoint.activity_id) == activity.id)
            )
            db.delete(activity)
            db.commit()
