# WP3 — Verve elevation implementation and verification

Requirements: [release checklist](../../../backend-release-changes.md) and
[work-package outline](2026-10-17-geojson-release-work-packages.md).

## Scope decisions

- Exclusively validated Verve 1.0 files. Other formats and generic attachments
  retain their existing behavior.
- Internal sea-level storage remains unchanged. No provenance fields, migrations,
  automatic backfills, or replacement track builder.
- Import subtracts the EGM2008 geoid offset; export adds it.
- Grid validation is mandatory at backend startup. Missing, corrupt, or unreadable
  files are fatal; no skipping, identity fallback, or request-time download.
- Docker/runtime-image installation and architecture verification move to WP6.
- Integration tests use one Verve file and the already-tested converter for
  expected stored heights. Independent numeric control points stay in the
  existing converter tests.

## Implementation

- The existing `parse_track` accepts an optional validated `verve_data` model.
  Canonical Verve import and recognized-Verve reprocessing supply it; other callers
  perform no elevation conversion.
- Conversion finishes before statistics or writes. Reprocessing reads original
  source bytes, and exports never mutate stored heights.
- The existing spatial exporter converts heights and orders segments/samples.
  Unavailable spatial coordinates or heights fail explicitly.
- The API lifespan verifies the local grid before accepting requests, including
  when a previous application instance populated the converter cache.
- CI installs the existing checksum-pinned grid before running pytest.

## Verification

- RED: simplified import round-trip failed on unconverted stored heights;
  missing/corrupt-grid startup tests failed because the backend started;
  unreadable-grid coverage exposed an unwrapped permission error.
- GREEN: 63 focused tests passed, including existing file-based import,
  auto-import, repeated reprocessing, and speed-summary coverage.
- Ruff lint, formatting checks, and ty passed on all nine changed Python files.
- Full suite: **583 passed, 15 failed**, with 255 warnings, in 101.31 seconds.
  The failures match the documented WP1/WP2 baseline: no new failing tests.
- Independent read-only review: no substantive findings.
- Docker/image verification remains deferred to WP6.

Focused command:

```bash
uv run pytest tests/test_elevation.py tests/test_verve_elevation.py tests/routes/test_verve_import.py tests/test_verve_speed_units.py -q --tb=short --show-capture=no
```

Full-suite command: `uv run pytest -q --tb=short --show-capture=no`.

The full suite is not green. Its 15 existing offsetless-Verve expectations remain
assigned to WP6, as detailed in the [WP1 report](2026-10-17-geojson-wp1-validation.md):

| Failing test | Cases |
| --- | --- |
| `test_activity.py::test_import_verve_resolves_offsetless_times` | 2 |
| `test_activity_display_timezone.py::test_verve_declared_zone_wins_over_gps_and_owner_setting` | 4 |
| `test_timezone_files.py::test_timezone_file_upload_persists_instants_and_heart_rates` | 8 |
| `test_timezone_files.py::test_timezone_file_export_import_preserves_times_zone_and_heart_rates` | 1 |

Implementation remains in the existing feature checkout. The WP3 commit excludes
unrelated staged and untracked files. No merge, push, or deployment is included.

See [elevation installation and compatibility notes](../../verve-elevation.md)
for the mandatory local grid and explicit reprocessing of earlier Verve imports.
