# GeoJSON 1.0 release work packages

Each package is a separate tracking unit with its own deliverable and acceptance criteria. The release checklist and current code are the starting points; the old ledger is not authoritative.

## WP1 — Core file validation

**Goal:** Make the core Verve file model enforce the release contract.

**Starting point:** Geometry requirements, array alignment, null geometry serialization, and speed conversion already have committed changes.

**Work:**

- Verify those changes against the release checklist and preserve their regression coverage.
- Require explicit UTC offsets on `startTime` and every `coordTimes` timestamp.
- Preserve optional statistics, partial summaries, nullable sensor arrays, and null sensor positions.
- Keep application timezone fallback separate from conforming file validation.

**Acceptance:**

- Missing geometry and missing timestamps fail independently.
- Zero- and one-position spatial lines fail; valid two-position lines succeed.
- Summary-only file models serialize explicit null geometry and empty timestamps.
- Offsetless file timestamps fail; UTC and numeric offsets preserve their instants.
- Omitted statistics and partial summaries remain accepted.

**Boundary:** Swimming validation belongs to WP5; database-backed import belongs to WP2. Export is deferred separately.

**Completion:** [x] Contract reviewed · [x] Changes tested · [x] Checks passed

**Release verification:** [WP6 evidence](2026-10-19-geojson-wp6-release-verification.md), including the reconciled timestamp fixtures and final passing suite.

## WP2 — Verve import and segment preservation

**Goal:** Import supported Verve activities through the canonical import path and preserve supported samples and supplied summaries during reprocessing.

**Work:**

- Handle spatial tracks, non-spatial sensor series, and summary-only activities.
- Reject mixed spatial/non-spatial features and fractional power samples in the Pydantic model before import writes.
- Preserve segment order, sample order, zeros, and missing sensor positions.
- Keep `_import_verve_file` as the validation entry point; retain the existing GeoJsonTrack conversion.
- Preserve supplied summaries, including zeros and partial or empty metric summaries; calculate wholly missing or null metric summaries from available samples.
- Verify speed conversion for stored summary fields and prevent repeated conversion.
- Keep the fast sniffer unchanged; validate recognized Verve sources before reprocessing and pass the validated model to the shared statistics helper.
- Use reviewed JSON files in integration tests for import, auto-import, and reprocessing.

**Acceptance:**

- Supported activity shapes import successfully and can be reprocessed repeatedly.
- Mixed geometry fails schema validation before writes; non-spatial samples have null stored locations.
- Sensors retain their alignment and reported zeros.
- Summary-only import and reprocessing succeed without track points.
- Reprocessing preserves supplied summaries and speed units while calculating missing metrics where possible.

**Boundary:** No migrations or new track builder. Generic track attachment remains unchanged. Export support, serialization, and export warnings are a separate follow-up; elevation, cadence, and swimming semantics remain in WP3–WP5.

**Dependencies:** WP1; coordinate elevation handling with WP3.

**Completion:** [x] Canonical paths connected · [x] File-based integration tested · [x] Focused checks passed

**Results:** [WP2 implementation and verification](2026-10-17-geojson-wp2-import.md).

## WP3 — Verve file elevation conversion

**Goal:** Convert Verve file ellipsoidal heights to existing sea-level storage on import and reverse the conversion on export.

**Work:**

- Apply the existing EGM2008 converter exclusively at validated Verve file import/export boundaries.
- Preserve internal sea-level storage, supplied summaries, and original source bytes.
- Convert before calculated statistics or writes; reprocess original Verve sources without accumulating conversions.
- Require the checksum-verified local grid at backend startup; missing, corrupt, or unreadable grids abort startup.
- Install the pinned grid locally and in CI for verification; do not skip real-grid tests.

**Acceptance:**

- Verve imports store sea-level heights; Verve exports restore ellipsoidal heights.
- Negative heights and already converted values remain correct.
- Repeated import/export and reprocessing do not double-convert.
- Missing or corrupt required grids cause explicit failures.
- Backend startup fails explicitly without a verified grid.
- Other file formats retain their existing behavior.

**Boundary:** Verve files only. No FIT, GPX, non-Verve GeoJSON, generic attachment, provenance schema, migration, or storage changes. Dockerfile changes and runtime-image deployment/verification belong to WP7.

**Completion:** [x] Boundary decision settled · [x] Integration verified · [x] Checks recorded

**Results:** [WP3 implementation and verification](2026-10-18-geojson-wp3-elevation.md). Full-suite failures remain the 15 existing WP1/WP2 offsetless-Verve expectations assigned to WP6.

## WP4 — Cadence semantics

**Goal:** Store cadence consistently as RPM and return activity-appropriate cadence without incorrectly doubling values.

**Work:**

- Trace cadence from FIT, GPX, and Verve through the locked parser and backend.
- Establish which sources provide total steps, two-step strides, or crank revolutions.
- Resolve normalization ownership from actual behavior.
- Store nullable fractional RPM for every activity; the user generates the model's migration afterward.
- Convert Verve running steps/min to RPM on import, then convert stored RPM to total steps/min in backend responses and Verve export.
- Apply response conversion to track samples, collection samples, and segment statistics using the current stored activity type.
- Preserve cycling RPM and other sports’ cadence; document their counted motion.
- Cover samples and supplied summaries within existing storage capabilities.

**Acceptance:**

- Running Verve steps/min become stored RPM and return as total steps/min; repeated processing does not accumulate conversion.
- FIT/GPX parser values retain the existing RPM convention; known parser gaps remain upstream follow-ups.
- Cycling RPM remains unchanged.
- Other sports’ cadence is retained.
- Nulls, zeros, and repeated round trips remain correct.

**Boundary:** No new cadence summary storage or blanket source conversion is assumed. Any required upstream change is identified explicitly.

**Completion:** [x] Source behavior established · [x] Normalization decision settled · [x] Regression cases verified

**Results:** [WP4 implementation and verification](2026-10-18-geojson-wp4-cadence.md). No migration file is generated; cadence summaries retain existing storage limitations.

## WP5 — Swimming metadata 1.0

**Goal:** Make wire validation and internal conversion conform to the swimming contract.

**Work:**

- Preserve fractional pool lengths and lap/set distances; remove integer truncation.
- Allow counts without details and details without counts.
- Validate count/array equality, zero-based indices, and supplied inclusive lap references.
- Accept non-null scalar zeros; reject metadata containing only unknown, null, or empty values.
- Require offset-qualified wire timestamps and compare interval boundaries as instants.
- Validate recognized swimming envelopes directly, preventing arbitrary-dictionary fallback.
- Validate recognized core swimming metadata on activity creation and PATCH while preserving application timezone fallback and custom fields.
- Preserve elapsed interval durations, separate rest, and length-based SWOLF meaning without enforcing exact arithmetic beyond source precision.

**Acceptance:**

- Fractional values survive wire → internal → wire conversion.
- Counts-only, details-only, and zero-only scalar payloads validate.
- Invalid counts, indices, references, timestamps, and empty-only metadata fail.
- Set elapsed time includes internal pauses; lap SWOLF uses lap duration and strokes.

**Boundary:** Arbitrary core metadata remains supported. Core timestamp validation is owned by WP1.

**Completion:** [x] Wire contract tested · [x] Internal conversion tested · [x] Checks passed

**Results:** [WP5 implementation and verification](2026-10-18-geojson-wp5-swimming.md). Final full suite: 686 passed and the same 15 existing WP1/WP2 offsetless-Verve failures assigned to WP6. Validation lives in the Pydantic models; the existing untracked swimming validation helper remains unused and untouched.

## WP6 — Release verification and documentation

**Goal:** Produce current evidence that the release checklist is satisfied.

**Work:**

- Run focused package tests and the full suite with PostgreSQL/PostGIS, Redis, and object storage.
- Run required Ruff, formatting, and type checks on changed Python files.
- Update obsolete fixtures while preserving intentional application fallback coverage.
- Verify actual import/export endpoints, reprocessing, and relevant RLS behavior.
- Record every release requirement as complete, blocked, or explicitly deferred with evidence.
- Document supported behavior, compatibility changes, source conventions, and elevation grid deployment.

**Acceptance:**

- WP1–WP5 and WP7 have recorded acceptance results.
- Required checks pass; unresolved failures are identified and explained.
- Documentation describes the delivered code and deployment requirements.
- WP7 provides evidence that the runtime image satisfies the mandatory elevation-grid startup requirement.
- Unrelated untracked files and generated artifacts remain outside release changes.

**Dependencies:** Final completion follows WP1–WP5 and WP7. Establish a test baseline early.

**Completion:** [x] Integration verified · [x] Full checks recorded · [x] Release documentation reconciled · [ ] Final release sign-off

**Results:** [WP6 verification and requirement register](2026-10-19-geojson-wp6-release-verification.md). Final WP6 suite: **718 passed**. Ruff, formatting, and ty passed across 32 release Python files; fixture artifacts and the 18-table RLS guard passed. WP7 now supplies local image evidence for both architectures; deployment still requires the user-generated cadence migration. Broader export remains explicitly deferred.

## WP7 — Docker elevation grid deployment

**Goal:** Ship runtime images containing the verified EGM2008 grid required by WP3, ready for offline Verve elevation conversion.

**Work:**

- Install the existing pinned grid during the Docker build using the checksum-verifying downloader; fail the build on download or checksum errors.
- Copy the verified artifact into the runtime image, configure `VERVE_EGM2008_GRID`, and ensure the normal runtime user can read it.
- Exclude local `data/proj/` artifacts from the build context so developer files cannot replace the reproducible installation.
- Verify conversion using the built image without network access; retain explicit startup failures for missing, corrupt, or unreadable grids.
- Build and verify both `linux/amd64` and `linux/arm64` images locally; leave CI and the release procedure unchanged.
- Document the image grid path, configuration overrides, and deployment prerequisites.

**Acceptance:**

- Both release architectures contain the checksum-pinned grid and perform a known conversion as the normal runtime user without downloading anything at startup or during requests.
- A missing or corrupt build artifact cannot produce a successful release image.
- An invalid runtime grid override aborts backend startup explicitly.
- Local unverified grid files cannot enter the runtime image through the build context.

**Boundary:** Container packaging and local verification only. Reuse WP3's converter, downloader, and startup validation. No changes to CI, release jobs, tagging, publishing, deployment procedures, storage, file-format behavior, or conversion semantics. Local and pytest CI grid installation already belong to WP3.

**Dependencies:** WP3. Complete before WP6's final release sign-off.

**Completion:** [x] Verified artifact packaged · [x] Both architectures verified offline · [x] Deployment documented

**Results:** [WP7 implementation and local image evidence](2026-10-19-geojson-wp7-docker-elevation.md). Both architectures built and passed all five offline checks; cache reuse, build-context exclusion and packaging failure probes passed. Full suite: **722 passed**. CI and release procedures remain unchanged.
