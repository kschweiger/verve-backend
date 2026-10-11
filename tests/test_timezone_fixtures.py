from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

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
