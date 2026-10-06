import json
from datetime import UTC, datetime
from importlib import resources
from zoneinfo import ZoneInfo

import pytest
from geo_track_analyzer import FITTrack
from pytest_mock import MockerFixture


def gpx_bytes(times: list[str]) -> bytes:
    points = "".join(
        f'<trkpt lat="52.52" lon="13.405"><time>{time}</time></trkpt>' for time in times
    )
    return (
        '<gpx version="1.1" creator="test"><trk><trkseg>'
        + points
        + "</trkseg></trk></gpx>"
    ).encode()


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        pytest.param("2026-07-01T10:00:00Z", 10, id="utc-instant"),
        pytest.param("2026-07-01T10:00:00+02:00", 8, id="offset-instant"),
        pytest.param("2026-07-01T10:00:00", 8, id="local-wall-time"),
    ],
)
def test_gpx_uses_gps_zone_and_respects_timestamp_offsets(
    timestamp: str,
    expected: int,
) -> None:
    from verve_backend.api.common.track import parse_track

    parsed = parse_track(
        file_name="track.gpx",
        file_content=gpx_bytes([timestamp]),
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert parsed.timezone.key == "Europe/Berlin"
    time = parsed.track.track.segments[0].points[0].time
    assert time is not None
    assert time.astimezone(UTC) == datetime(2026, 7, 1, expected, tzinfo=UTC)


def test_request_override_skips_gps_lookup(mocker: MockerFixture) -> None:
    from verve_backend.api.common import timezone
    from verve_backend.api.common.track import parse_track

    lookup = mocker.spy(timezone, "infer_iana_timezone_from_coordinates")
    parsed = parse_track(
        file_name="track.gpx",
        file_content=gpx_bytes(["2026-07-01T10:00:00+02:00"]),
        fallback_timezone=ZoneInfo("Europe/Berlin"),
        timezone_name="America/Los_Angeles",
    )
    assert parsed.timezone.key == "America/Los_Angeles"
    assert parsed.track.track.segments[0].points[0].time.astimezone(UTC) == datetime(
        2026, 7, 1, 8, tzinfo=UTC
    )
    lookup.assert_not_called()


def test_mixed_gpx_times_preserve_each_instant() -> None:
    from verve_backend.api.common.track import parse_track

    parsed = parse_track(
        file_name="track.gpx",
        file_content=gpx_bytes(["2026-07-01T10:00:00", "2026-07-01T08:10:00Z"]),
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert [p.time.astimezone(UTC) for p in parsed.track.track.segments[0].points] == [
        datetime(2026, 7, 1, 8, tzinfo=UTC),
        datetime(2026, 7, 1, 8, 10, tzinfo=UTC),
    ]


def test_geojson_without_geometry_uses_fallback_without_lookup(
    mocker: MockerFixture,
) -> None:
    from verve_backend.api.common import timezone
    from verve_backend.api.common.track import parse_track

    lookup = mocker.spy(timezone, "infer_iana_timezone_from_coordinates")
    data = {
        "type": "Feature",
        "geometry": None,
        "properties": {"coordTimes": ["2026-07-01T10:00:00", "2026-07-01T10:10:00"]},
    }
    parsed = parse_track(
        file_name="track.json",
        file_content=json.dumps(data).encode(),
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert parsed.no_geometry
    assert parsed.timezone.key == "America/Los_Angeles"
    assert parsed.track.track.segments[0].points[0].time.astimezone(UTC) == datetime(
        2026, 7, 1, 17, tzinfo=UTC
    )
    lookup.assert_not_called()


def test_first_timed_point_determines_whole_track_zone(
    mocker: MockerFixture,
) -> None:
    from verve_backend.api.common import timezone
    from verve_backend.api.common.track import parse_track

    lookup = mocker.spy(timezone, "infer_iana_timezone_from_coordinates")
    data = (
        '<gpx version="1.1" creator="test"><trk><trkseg>'
        '<trkpt lat="34.05" lon="-118.24"/>'
        '<trkpt lat="52.52" lon="13.405"><time>2026-07-01T10:00:00Z</time></trkpt>'
        '<trkpt lat="34.05" lon="-118.24"><time>2026-07-02T10:00:00Z</time></trkpt>'
        "</trkseg></trk></gpx>"
    ).encode()
    parsed = parse_track(
        file_name="track.gpx",
        file_content=data,
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert parsed.timezone.key == "Europe/Berlin"
    lookup.assert_called_once_with(latitude=52.52, longitude=13.405)


@pytest.mark.parametrize(
    ("override", "expected_zone"),
    [
        pytest.param("Europe/Berlin", "Europe/Berlin", id="request-zone"),
        pytest.param(None, "America/Los_Angeles", id="ocean-gps-fallback"),
    ],
)
def test_fit_zone_selection_preserves_decoder_instants(
    override: str | None,
    expected_zone: str,
) -> None:
    from verve_backend.api.common.track import parse_track

    data = resources.files("tests.resources").joinpath("MyWhoosh_1.fit").read_bytes()
    decoded = FITTrack(data)
    parsed = parse_track(
        file_name="track.fit",
        file_content=data,
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
        timezone_name=override,
    )
    assert parsed.timezone.key == expected_zone
    assert [p.time for s in parsed.track.track.segments for p in s.points] == [
        p.time for s in decoded.track.segments for p in s.points
    ]


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        pytest.param(52.52, 13.405, "Europe/Berlin", id="berlin-land"),
        pytest.param(0, -140, None, id="ocean"),
        pytest.param(91, 0, None, id="invalid-latitude"),
        pytest.param(0, 181, None, id="invalid-longitude"),
        pytest.param(float("nan"), 0, None, id="nan"),
        pytest.param(0, float("inf"), None, id="infinite"),
    ],
)
def test_coordinate_lookup_returns_only_land_zones(
    latitude: float,
    longitude: float,
    expected: str | None,
) -> None:
    from verve_backend.core.timezone_lookup import infer_iana_timezone_from_coordinates

    assert (
        infer_iana_timezone_from_coordinates(
            latitude=latitude,
            longitude=longitude,
        )
        == expected
    )


def test_partial_geojson_geometry_uses_first_real_timed_coordinate(
    mocker: MockerFixture,
) -> None:
    from verve_backend.api.common import timezone
    from verve_backend.api.common.track import parse_track

    lookup = mocker.spy(timezone, "infer_iana_timezone_from_coordinates")
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": None,
                "properties": {"coordTimes": ["2026-07-01T10:00:00Z"]},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[13.405, 52.52, 10]],
                },
                "properties": {"coordTimes": ["2026-07-01T10:10:00Z"]},
            },
        ],
    }
    parsed = parse_track(
        file_name="track.json",
        file_content=json.dumps(data).encode(),
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert parsed.timezone.key == "Europe/Berlin"
    lookup.assert_called_once_with(latitude=52.52, longitude=13.405)


def test_standalone_geojson_does_not_use_verve_timezone_property() -> None:
    from verve_backend.api.common.track import parse_track

    data = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[-118.24, 34.05, 10]]},
        "properties": {
            "timezone": "Europe/Berlin",
            "coordTimes": ["2026-07-01T10:00:00"],
        },
    }
    parsed = parse_track(
        file_name="track.json",
        file_content=json.dumps(data).encode(),
        fallback_timezone=ZoneInfo("Europe/Berlin"),
    )
    assert parsed.timezone.key == "America/Los_Angeles"
    assert parsed.track.track.segments[0].points[0].time.astimezone(UTC) == datetime(
        2026,
        7,
        1,
        17,
        tzinfo=UTC,
    )


def test_ocean_track_uses_fallback_without_inventing_iana_zone() -> None:
    from verve_backend.api.common.track import parse_track

    data = gpx_bytes(["2026-07-01T10:00:00Z"]).replace(
        b'lat="52.52" lon="13.405"',
        b'lat="0" lon="-140"',
    )
    parsed = parse_track(
        file_name="track.gpx",
        file_content=data,
        fallback_timezone=ZoneInfo("America/Los_Angeles"),
    )
    assert parsed.timezone.key == "America/Los_Angeles"
    assert parsed.track.track.segments[0].points[0].time.astimezone(UTC) == datetime(
        2026,
        7,
        1,
        10,
        tzinfo=UTC,
    )
