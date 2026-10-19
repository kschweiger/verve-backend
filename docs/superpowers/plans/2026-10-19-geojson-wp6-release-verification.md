# WP6 — Release verification and documentation

Date: 2026-10-19. Requirements: [release checklist](../../../backend-release-changes.md)
and [work packages](2026-10-17-geojson-release-work-packages.md).

## Scope and environment

Base: `3b681b82508fe7018e67f75976651132f0ed3c10`, branch
`refactor/geojson-final`. Results apply to this base plus the WP6 working diff.
Use the approved conversation plan: establish baseline; repair strict fixtures;
verify routes, reprocessing, RLS and serializer; reconcile documentation and checks.
No commits, merge, push, production reprocessing, deployment or migration generation.
Preserve unrelated staged/untracked files; intentionally update the existing
untracked implementation ledger. Coverage output and temporary artifacts are excluded.

- Python 3.14.0; `uv sync --locked --group test --no-dev` succeeded.
- Established services: PostgreSQL 18.6 (Homebrew), PostGIS 3.6.4, Redis 8.8.0,
  and the configured S3-compatible test store.
- Schema `api`; 18 RLS-enabled tables observed before verification.
- CI still uses PostgreSQL 17. Local results cover PostgreSQL 18; existing CI
  does not establish that supported-version requirement.

## Evidence

| Check | Result |
| --- | --- |
| Baseline full suite | Exit 1: 686 passed, 15 failed, 294 warnings, 122.50 seconds |
| Portable-file regression before fixture repair | Exit 1: 4 failed, 2 passed; missing offsets and explicit generators |
| Focused timestamp/import/integration checks | Exit 0: 103 passed, 80 warnings, 133.88 seconds |
| Final full suite | Exit 0: 718 passed, 307 warnings, 172.78 seconds |
| Ruff lint, formatting, ty | Exit 0 for each check on all 32 changed release Python files |
| Fixture checksum/ZIP | Regenerated; `--check` exit 0 |
| RLS guard and grid | Exit 0; 18 sensitive tables protected in schema `api`; grid hash verified and real conversion succeeded |
| Diff/review | `git diff --check` exit 0; independent read-only review found no actionable issues |

All 15 baseline failures match WP1–WP5: two inline offsetless imports, four
inline display-zone cases, eight shared-fixture uploads, and one fixture round
trip. They expected 200 where strict file validation correctly returned 422.

## Requirement register

Application rows below are complete based on the focused and final full-suite
runs. Explicit deferrals remain outside the approved delivery boundary, rather
than establishing full exporter conformance. WP7's local image evidence below
now resolves the image packaging gate; cadence upgrade compatibility remains
blocked on the user-generated migration.

| Requirement | Status | Evidence / limitation |
| --- | --- | --- |
| Required nullable geometry, explicit timestamps, two-position minimum | Complete | Core geometry/file tests |
| Array alignment, null sensor positions, zero values | Complete | Geometry and file-backed imports |
| Explicit timestamp offsets, independent fields and request overrides | Complete | New rejection-without-writes cases; portable fixtures |
| Optional/partial/empty summaries and nullable arrays | Complete | Core files and import cases |
| Speed 10 m/s ↔ 36 km/h without repeated conversion | Complete | Speed-unit suite and public-route serializer reimports |
| Spatial, non-spatial, summary-only canonical imports | Complete | File-backed coverage through both import routes |
| Mixed geometry/fractional power rejected before writes | Complete | Existing invalid-file database/object snapshots |
| Segment/sample order, original source bytes, supplied summaries | Complete | Import, repeat reprocessing and new admin-route tests |
| Sea-level storage/ellipsoidal boundary, negative heights, no drift | Complete | Real-grid, Verve elevation and serializer/admin cases |
| Mandatory grid, fatal startup errors, other formats unchanged | Complete | Existing grid/startup and non-Verve tests in the passing full suite |
| Running cadence source/output classification, cycling/other retention | Complete | Cadence, track/collection, serializer/admin cases |
| Fractional RPM, nulls/zeros, rounding and repeated processing | Complete | Cadence and admin/serializer cases |
| FIT/GPX conventions and other sports' counted motions | Complete | Cadence documentation; existing parser behavior retained |
| Swimming fractional values, counts/details, meaningful zeros | Complete | Swimming model/conversion/API suites |
| Swimming indices, references, offsets, envelopes, elapsed/rest/SWOLF | Complete | Swimming suites and imported metadata cases |
| Arbitrary metadata and application timezone fallback | Complete | Existing manual/GPX/generic and swimming application tests |
| Imported activity/raw-source/sample RLS and admin authorization | Complete | New two-user real-RLS tests; existing admin checks |
| Existing spatial serializer validates and publicly reimports | Complete | New serializer reimport cases |
| Public export API, non-spatial/summary export, broader serialization | Explicitly deferred | No export endpoint exists; preserve agreed export boundary |
| Cadence summary/minimum persistence and upstream parser enhancements | Explicitly deferred | Existing storage limits; original bytes retained |
| Provenance schema and automatic historical rewrites | Explicitly deferred | WP3 retains storage semantics and explicit reprocessing |
| Grid-bearing runtime image, both release architectures | Complete | [WP7 local image evidence](2026-10-19-geojson-wp7-docker-elevation.md): both platforms, offline conversion/startup, invalid overrides and packaging failures |
| Cadence upgrade compatibility | Blocked | User-generated migration absent; pytest recreates model tables |
| Required checks and current documentation | Complete | Commands below passed; supported behavior and limits documented |

## Verification commands and release gates

```bash
uv run --no-sync pytest -q --tb=short --show-capture=no
uv run --no-sync python scripts/timezone_fixtures.py --check
ENVIRONMENT=testing uv run --no-sync python -m verve_backend.cli.ensure_rls
git diff --check
```

Focused command (103 passed):

```bash
uv run --no-sync pytest tests/test_timezone_fixtures.py tests/routes/test_activity_display_timezone.py tests/routes/test_timezone_files.py tests/routes/test_verve_import.py -q --tb=short --show-capture=no
```

The full suite additionally covers all core, speed-unit, elevation, cadence,
swimming, track/collection, admin and RLS tests. The 19 new cases replace two
obsolete cases, bringing the total from 701 to 718. Offset rejection checks each
timestamp member independently through both routes with and without a request
override and asserts unchanged database/object state. Public admin tests cover
two rebuilds of running, non-spatial and summary-only files; serializer tests
reimport running and spatial elevation files twice through the public route.

All three final checks passed over the same 32-file set, selected as the sorted
union of `git diff --name-only 8e3117c^ HEAD -- '*.py'` and
`git diff --name-only -- '*.py'`. This includes the release's geometry/speed/grid
work and WP1–WP6, excluding unrelated untracked Python modules:

```bash
uv run --no-sync ruff check <32-release-python-files>
uv run --no-sync ruff format --check <32-release-python-files>
uv run --no-sync ty check --output-format concise <32-release-python-files>
```

Ruff initially flagged one combined assertion (PT018); splitting it preserved
behavior and all final checks passed. Initial test-only dependency installation
was followed by `uv sync --locked --group dev` to restore locked type-check tools.

The required grid hash is
`4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a`.
The configured grid produced sea-level height `53.980892181396484` m from
`(longitude=11.5, latitude=48, ellipsoidal_height=100)`. Independent numeric
control points and missing/corrupt/unreadable startup cases passed in the full suite.

Warnings retain the baseline categories: deprecated Starlette/httpx TestClient
integration, SQLAlchemy user-settings/image cleanup row counts, and a null subtype
lookup in existing activity creation. None failed the suite; cleanup warning
counts increase with the new integration cases. These existing warnings were
recorded rather than suppressed.

## Execution rulings and review boundaries

- Retained the approved checkout and unrelated untracked inputs; no new worktree
  or commits. Cost if wrong: unrelated files would enter the release; final
  change inventory was inspected to prevent that.
- New coverage for correct existing behavior is characterization; no production
  mutation was introduced to manufacture failing tests. Portable fixture
  regressions were observed failing before repair. Cost if wrong: weaker proof
  of a regression; the independent reviewer checked the assertions and real paths.
- Used established PostgreSQL 18.6 for supported-version evidence and recorded
  PostgreSQL 17 CI separately. No CI provisioning change. Cost if wrong: CI
  remains unable to reproduce the supported-version environment.
- No public export route exists, so no HTTP 501 handler was added. Broader export
  remains deferred as approved. Cost if wrong: clients expecting export have no
  public endpoint; documentation states this explicitly.
- Independent review declined final check results because they were still
  running; this report supplies the subsequent successful outputs.
- Real task bodies ran in eager mode against Redis; deployed worker/broker
  execution was outside this test plan. Cost if wrong: deployment-only worker
  failures remain possible and are not claimed as tested.
- Migration upgrade compatibility and runtime images were outstanding at WP6
  close. WP7's local built-image checks now resolve the image gate; model-created
  tests still cannot establish migration upgrade compatibility.
- Broader serializer preservation was set aside within the approved export
  boundary and its current limitations are documented.

No actionable review findings or deferred minor findings were reported.

WP7 addendum: local `linux/amd64` and `linux/arm64` images now supply the
checksum-pinned grid, runtime-user readability, offline conversion/startup,
invalid-override failures, build-context exclusion and packaging-failure evidence.
See the [WP7 report](2026-10-19-geojson-wp7-docker-elevation.md) for image IDs and
commands. These are built-image checks, not host-only grid tests. CI and release
procedures remain unchanged. Deployment still requires the user-generated cadence
migration; model-created pytest tables cannot establish its upgrade compatibility.
