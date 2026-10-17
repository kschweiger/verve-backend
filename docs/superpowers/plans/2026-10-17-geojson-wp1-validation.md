# WP1 — Core file validation results

Date: 2026-10-17.

Requirements: [release checklist](../../../backend-release-changes.md) and
[WP1 work package](2026-10-17-geojson-release-work-packages.md).

## Delivered behavior

- `startTime` and every `coordTimes` item require timezone-aware timestamps.
- Offsetless strings, naive Python datetimes, and numeric epochs are rejected.
- UTC and numeric offsets preserve their instants through serialization.
- Declaring an activity display timezone does not supply a missing timestamp offset.
- Required nullable geometry, two-position spatial lines, and array alignment remain enforced.
- Summary-only models preserve `geometry: null` and `coordTimes: []`.
- Optional statistics, partial summaries, nullable sensor arrays, missing sensor positions,
  reported zeros, and arbitrary core metadata retain their existing behavior.

The schema uses a shared `FileTimestamp` type with string/datetime input validation
and Pydantic's timezone-awareness check. Application timezone fallback remains in
the existing parser utilities. Swimming validation and database-backed import/export
changes remain assigned to their own packages.

## Verification

- Initial geometry baseline: **10 passed**.
- New timestamp regressions before implementation: **22 expected failures**, all
  accepting timestamps that should have raised `ValidationError`; **30 passed**.
- Geometry and timestamp tests after implementation: **52 passed**.
- Final focused suite, including optional-data coverage: **115 passed**.
- Ruff lint, Ruff formatting, and ty checks on all three changed Python files: **passed**.
- Full suite: **539 passed, 15 failed**, with 217 warnings, in 40.19 seconds.
- Independent read-only review: no critical, important, or minor findings.

Focused command:

```bash
uv run pytest tests/test_verve_geometry.py tests/test_verve_file.py tests/test_verve_file_meta_data.py tests/test_verve_speed_units.py tests/test_track_timezones.py -q --tb=short
```

Checks:

```bash
uv run ruff check verve_backend/schema/verve_file.py tests/test_verve_geometry.py tests/test_verve_file.py
uv run ruff format --check verve_backend/schema/verve_file.py tests/test_verve_geometry.py tests/test_verve_file.py
uv run ty check --output-format concise verve_backend/schema/verve_file.py tests/test_verve_geometry.py tests/test_verve_file.py
```

Full-suite command: `uv run pytest -q --tb=short`.

## WP6 handoff: obsolete offsetless Verve expectations

All 15 failures expect successful uploads of offsetless Verve input. Strict core
validation now correctly returns HTTP 422. The approved WP1 plan explicitly leaves
these expectation and shared-fixture updates to WP6; the full suite is not green.

| Failing test | Cases |
| --- | --- |
| `tests/routes/test_activity.py::test_import_verve_resolves_offsetless_times` | Owner fallback and `Europe/Berlin` request override: 2 |
| `tests/routes/test_activity_display_timezone.py::test_verve_declared_zone_wins_over_gps_and_owner_setting` | File/request zones through import/auto routes: 4 |
| `tests/routes/test_timezone_files.py::test_timezone_file_upload_persists_instants_and_heart_rates` | `verve-declared-zone`, `verve-gps-zone`, `verve-owner-fallback`, and `request-override`, each through auto/import routes: 8 |
| `tests/routes/test_timezone_files.py::test_timezone_file_export_import_preserves_times_zone_and_heart_rates` | Offsetless round-trip source upload: 1 |

Shared files needing reconciliation are `verve-berlin-declared-new-york.json`,
`verve-berlin-no-zone.json`, and `verve-no-geometry-no-zone.json` under
`tests/resources/timezones/`. The two other failing test functions also construct
offsetless Verve input inline.

WP6 must preserve GPX/generic-parser fallback tests, use offset-qualified timestamps
for conforming Verve uploads, ensure display-zone overrides preserve aware instants,
and regenerate the shared fixture digest/archive when fixture sources change.

## Execution decisions

- Kept the existing `refactor/geojson-final` checkout to preserve access to untracked
  release inputs. No merge or push is part of WP1.
- Used a temporary ledger in the existing `.superpowers` directory because the approved
  detailed plan was supplied in the conversation; this report preserves its results.
- Accepted `datetime.fromisoformat` syntax as specified in the approved plan; additional
  lexical restrictions, model mutation bypasses, swimming behavior, and application
  import/export consistency were outside this review's scope.

All WP1 core-model acceptance criteria have passing focused coverage. Final release
verification remains pending WP6's reconciliation of the 15 obsolete expectations.
