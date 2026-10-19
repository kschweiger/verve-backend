from __future__ import annotations

import json
from importlib import resources
from io import BytesIO
from zipfile import ZipFile

import pytest

from scripts.timezone_fixtures import build_archive, digest_sources


def test_digest_changes_when_fixture_name_or_bytes_change(tmp_path) -> None:
    source = tmp_path / "timezones"
    source.mkdir()
    fixture = source / "case.json"
    fixture.write_bytes(b"one")

    original = digest_sources(source)
    fixture.write_bytes(b"two")
    changed_bytes = digest_sources(source)
    fixture.rename(source / "renamed.json")
    changed_name = digest_sources(source)

    assert changed_bytes != original
    assert changed_name != changed_bytes


def test_archive_is_reproducible_and_contains_all_source_files(tmp_path) -> None:
    source = tmp_path / "timezones"
    source.mkdir()
    (source / "cases.json").write_text("{}", encoding="utf-8")
    (source / "sample.gpx").write_text("<gpx />", encoding="utf-8")

    first = build_archive(source)
    second = build_archive(source)

    assert first == second
    with ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == ["timezones/cases.json", "timezones/sample.gpx"]
        assert archive.read("timezones/cases.json") == b"{}"


@pytest.mark.parametrize(
    "file_name",
    [
        "verve-berlin-declared-new-york.json",
        "verve-berlin-declared-new-york-utc.json",
        "verve-berlin-no-zone.json",
        "verve-no-geometry-no-zone.json",
    ],
)
def test_portable_verve_fixtures_conform_to_file_contract(file_name: str) -> None:
    from verve_backend.schema.verve_file import VerveFeature

    source = json.loads(
        resources.files("tests.resources").joinpath("timezones", file_name).read_bytes()
    )
    parsed = VerveFeature.model_validate(source)
    assert isinstance(source["properties"]["generator"], str)
    assert parsed.properties.start_time.utcoffset() is not None
    for feature in parsed.features:
        assert all(
            time.utcoffset() is not None for time in feature.properties.coord_times
        )
