# WP5 — Swimming metadata 1.0 implementation

Requirements: [release checklist](../../../backend-release-changes.md),
[work package](2026-10-17-geojson-release-work-packages.md), and the finalized
swimming 1.0 specification in the sibling geojson-flavor repository.

## Decisions

- Validation belongs directly in the wire and core Pydantic models. The existing
  untracked `core/swimming_validation.py` remains unused and untouched.
- Reject missing/unsupported versions for recognized swimming metadata before
  the arbitrary-dictionary union can accept them. Preserve arbitrary other metadata.
- Preserve fractional measurements, scalar zeros, partial summaries, and the
  distinction between empty and unavailable arrays.
- Enforce count/array agreement, positional indices, inclusive references, finite
  numeric values, nonnegative integer counts, and interval order by UTC instant.
- Wire timestamps require offsets. Application create/PATCH retain timezone
  fallback and revalidate after normalization. PATCH preserves custom fields.
- Reuse WP1's timestamp parser without adding new lexical restrictions.
- Preserve supplied duration, rest, and SWOLF; no derivation, exact arithmetic
  checks, historical repair, migration, or non-spatial export expansion.
- Use the existing feature checkout to retain access to untracked release inputs.
  No merge, push, or deployment is included.

## Implementation and verification

- Core/wire constraints and conversion implemented. Initial regression run:
  **25 failed, 8 passed**, exposing the intended contract gaps.
- First focused model suite: **46 passed** after implementation.
- Added file-based explicit/auto import, repeated reprocessing, spatial export,
  rejected-upload atomicity, and activity API persistence coverage.
- Corrected the existing swim import fixture to use offsets and forward interval
  boundaries. Retained application timezone fallback and separate rejection tests.
- Final swimming model/API suite: **80 passed**, including reported precision,
  empty-array preservation, interval ordering, duration coercion, and atomic PATCH.
- Broader focused run before the review fix: **255 passed, 2 failed**. Both
  failures are existing WP1/WP2 offsetless-file expectations assigned to WP6.
- Independent read-only review found one duration-coercion gap: booleans were
  accepted as one-second internal durations. Four model cases and one atomic
  PATCH case reproduced it, then passed with Pydantic field validators in place.
- The first full run also identified a timezone-precedence fixture whose
  Los Angeles interval ended before it started. Corrected its fixed UTC end
  while retaining all timezone precedence cases and separate rejection coverage.
- Locked test dependency synchronization passed. Ruff lint, formatting, and ty
  checks passed on all **14 changed Python files**. Updated documentation examples
  validate against the production file and core Pydantic models.
- Final full suite: **686 passed, 15 failed**, with 294 warnings, in 135.01 seconds.
  All failures match the existing WP1/WP2 offsetless-Verve cases assigned to WP6;
  no WP5 failures remain.

## Verification commands

Final swimming model/API suite:

```bash
uv run pytest tests/test_swimming_contract.py tests/test_meta_data.py tests/test_verve_file_meta_data.py tests/routes/test_swimming_metadata.py -q --tb=short --show-capture=no
```

The broader focused command also included `tests/test_verve_file.py`,
`tests/test_verve_geometry.py`, `tests/routes/test_activity.py`, and
`tests/routes/test_verve_import.py`.

Full suite: `uv run pytest -q --tb=short --show-capture=no`.

Required Ruff lint, Ruff formatting checks, and `ty check --output-format concise`
passed for all changed Python files. `git diff --check` passed.

Remaining full-suite failures:

| Test | Cases |
| --- | --- |
| `test_activity.py::test_import_verve_resolves_offsetless_times` | 2 |
| `test_activity_display_timezone.py::test_verve_declared_zone_wins_over_gps_and_owner_setting` | 4 |
| `test_timezone_files.py::test_timezone_file_upload_persists_instants_and_heart_rates` | 8 |
| `test_timezone_files.py::test_timezone_file_export_import_preserves_times_zone_and_heart_rates` | 1 |

See [backend swimming contract](../../product-specs/verve-swimming-metadata.md).
