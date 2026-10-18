# WP4 — Cadence semantics implementation

Date: 2026-10-18.

Requirements: [release checklist](../../../backend-release-changes.md),
[work package](2026-10-17-geojson-release-work-packages.md), and the reviewed
decisions from this session.

## Contract

The database always stores RPM in the cycling convention, regardless of activity
type. Update the nullable cadence model to float; the user generates the migration
afterward. No dedicated column or annotation tests.

Running Verve samples count both feet: divide by two on import. The backend
multiplies stored RPM by two when returning running track samples, collection
samples, segment statistics, or Verve samples. Running means `Foot Sports` with
subtype `Run`, `Trail Run`, or `Treadmill`. Other sports receive no scaling.

Use source classification on import and the current stored classification on
output. Preserve nulls, zeros, alignment, segments, source bytes, and supplied
summaries. Round only Verve samples, after conversion, using Python's `round()`.

## Implementation checklist

- [x] Update model/response annotations without generating a migration.
- [x] Centralize classification and conversion in `core/cadence.py`.
- [x] Convert recognized Verve cadence once in shared parsing, including imports,
  attachments, and original-source reprocessing.
- [x] Convert track and collection responses using the shared response builder.
- [x] Convert segment cadence aggregates after SQL calculations.
- [x] Convert Verve sample output and preserve zero-only arrays.
- [x] Document API compatibility, historical reprocessing, and upstream gaps.
- [x] Record final focused, full-suite, lint, formatting, and type-check results.

The existing schema package imports its importer eagerly. Keep Verve runtime
validation imports local in the shared parser to avoid an import cycle.
Attachment cadence validation does not opt attachments into elevation conversion.

## Behavioral checks

Tests use a reviewed running JSON fixture and existing database/object-store
fixtures. Cover source subtype classification; spatial/non-spatial import and
repeated reprocessing; request type overrides; current-type response conversion;
mixed-activity collections; segment min/average/max; repeated spatial round trips;
zero-only versus unavailable arrays; fractional export rounding; source-model and
source-byte preservation; and unscaled FIT/GPX values.

## Boundaries

Keep FIT/GPX parsing in geo-track-analyzer. Nested Garmin GPX cadence is not exposed
as cadence, and FIT fractional cadence remains separate. No backend adapters,
dependency changes, summary storage, or non-spatial export expansion.

Apply the user-generated migration before deployment, preserve historical numeric
values, and reprocess earlier running Verve imports before relying on their new
response/export meaning. Clients must remove their own running-cadence doubling.

See [cadence behavior and deployment](../../verve-cadence.md).

## Verification results

- Before implementation: 16 failing cadence cases exposed missing normalization,
  missing response conversion, dropped zero-only arrays, and absent attachment
  validation. The remaining cases characterized preserved source behavior.
- Final focused suite: **130 passed**, including **28 cadence cases**.
- Ruff lint, Ruff formatting checks, and ty: **passed** on all six changed Python
  files. No dedicated column or annotation tests were added.
- Full suite: **611 passed, 15 failed**, with 266 warnings, in 105.12 seconds.
- Independent read-only review: no actionable bugs or regressions found.
- No migration, merge, push, or deployment was performed.

Focused command:

```bash
uv run pytest tests/test_cadence.py tests/routes/test_track.py tests/routes/test_collection.py tests/routes/test_verve_import.py tests/routes/test_admin.py tests/test_verve_elevation.py tests/test_verve_speed_units.py -q --tb=short --show-capture=no
```

Full-suite command: `uv run pytest -q --tb=short --show-capture=no`.

The full suite remains red with exactly the previously documented WP1/WP2
offsetless-Verve cases, assigned to WP6; no new failing tests were introduced:

| Failing test | Cases |
| --- | --- |
| `test_activity.py::test_import_verve_resolves_offsetless_times` | 2 |
| `test_activity_display_timezone.py::test_verve_declared_zone_wins_over_gps_and_owner_setting` | 4 |
| `test_timezone_files.py::test_timezone_file_upload_persists_instants_and_heart_rates` | 8 |
| `test_timezone_files.py::test_timezone_file_export_import_preserves_times_zone_and_heart_rates` | 1 |

Deployment handoff remains the agreed user-generated migration and reprocessing
of earlier running Verve sources. Cadence summary persistence, non-spatial export,
and FIT/GPX parser gaps remain explicitly deferred as above.
