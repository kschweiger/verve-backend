# WP2 — Verve import results

Date: 2026-10-17.

Requirements: [release checklist](../../../backend-release-changes.md),
[work package](2026-10-17-geojson-release-work-packages.md), and the scope decisions
made during implementation planning.

## Delivered behavior

- `_import_verve_file` remains the canonical validation entry point for import and
  auto-import. The existing `GeoJsonTrack` conversion is reused.
- The Pydantic model rejects mixed spatial/non-spatial features and fractional
  power samples, matching the existing integer power storage.
- `apply_verve_activity_data` takes a validated `VerveFeature`. Both import and
  stored-source reprocessing use it.
- Supplied average/maximum speed, heart-rate, and power summaries survive, including
  zeros and partial or empty metric summaries. Wholly missing or null metric
  summaries are calculated from usable samples. With no samples, unavailable
  summaries remain empty.
- Speed summaries convert from file m/s to stored km/h exactly once.
- Supplied dimensions, including zero moving duration, remain intact. File start
  time and duration remain authoritative when they differ from the samples.
- Summary-only import and reprocessing work without fabricated points. Empty
  segments are omitted from storage; populated segment/sample order and sensor
  null positions and zeros are preserved. Non-spatial samples have null locations.
- The sniffer remains a fast signature check. Reprocessing validates recognized
  Verve sources after sniffing, before replacing stored data.
- Generic parsing, generic track attachment, and export remain unchanged. No new
  track builder, dependencies, database tables, or migrations were added.

## File-based coverage

The integration tests use the 13 actual JSON files in
`tests/resources/verve_import/` with the configured database and object store.
They cover import, auto-import, repeated reprocessing, source-byte preservation,
and rejection/rollback behavior.

The additional compatibility fixture covers accepted property aliases and numeric
strings, empty segments, and authoritative activity dimensions. Its two
import-to-reprocessing tests failed before the validated-model fix. The two admin
timezone cases now use dedicated offset-qualified files, preserving their display
timezone checks without modifying shared timezone fixtures.

An independent read-only review identified the property-normalization mismatch;
passing the validated model addresses it and removes manual dictionary coercion.

## Verification

- Focused suite: **148 passed**, including **35 new file-backed acceptance cases**.
- Ruff lint, Ruff formatting checks, and ty: **passed** on all six changed Python files.
- Full suite: **574 passed, 15 failed**, with 252 warnings, in 91.66 seconds.
- The full-suite failure IDs exactly match the existing WP1 baseline: no new failures.

Focused command:

```bash
uv run pytest tests/routes/test_verve_import.py tests/routes/test_admin.py tests/test_verve_geometry.py tests/test_verve_file.py tests/test_verve_speed_units.py -q --tb=short --show-capture=no
```

Full-suite command:

```bash
uv run pytest -q --tb=short --show-capture=no
```

## Remaining release work

The 15 obsolete offsetless-Verve expectations remain assigned to WP6, as recorded
in the [WP1 verification report](2026-10-17-geojson-wp1-validation.md). The full
suite is not green.

Export support and its warnings/serialization/round-trip work are deferred to a
separate follow-up. Elevation semantics, cadence normalization, and swimming
conformance remain in WP3–WP5.

Implementation and verification were completed in the existing checkout.
