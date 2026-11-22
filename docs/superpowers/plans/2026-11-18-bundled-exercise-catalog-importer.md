# Bundled exercise catalog implementation plan

Updated 2026-11-18 after the independent schema review and user decisions.
This replaces the earlier RepDB-oriented schema assumptions in this plan.

## Goal and accepted decisions

Synchronize the packaged Verve catalog offline, after Alembic and before API
startup. Preserve exercise identity and store detailed muscle assignments and
display groups in the database. Labels remain locale JSON resources.

- Exercise identity is a UUID plus permanent unique code. Remove provider-specific
  source/source_id/source_revision columns.
- Muscles and display groups retain UUIDs and unique codes. Link tables retain
  composite keys, RESTRICT foreign keys, and explicit relationship objects.
- Roles use the existing SQLModel enum pattern: a PostgreSQL enum stores PRIMARY
  and SECONDARY, and ORM loading returns ExerciseMuscleRole values. No custom type.
- Replace the unapplied feature migration with a fresh initial catalog revision
  on the existing parent 82ab19d34f60. The user confirmed no applied deployment.
- A checkpoint stores catalog_code (primary key), content_hash, and sync_version.
  Data and checkpoint share one transaction. No per-exercise import revision.
  Only the current catalog retains a checkpoint, because group definitions are
  global. Changing catalogs invalidates the previous checkpoint atomically.
- The complete display-group definition follows the input, including deletion of
  omitted groups and their links. Retained group codes keep their UUIDs.
- Omitted exercises and muscles remain stored. Explicit is_active:false retires
  an exercise without changing its identity or links.
- No new privilege model, user_id, names, weights, drawing data, or RLS changes.
- jsonschema is a test dependency. Runtime validation uses existing Pydantic.
- Commit only on explicit user instruction. The user approved committing this state.
- The user explicitly waived a separate migration execution check. Use the normal
  test metadata.create_all setup, which recreates the established test schema.

## Implementation steps

- [x] Write failing parser, startup, role-loading, and importer behavior tests.
- [x] Implement strict JSON parsing, structural and semantic validation, packaged
  resource loading, and canonical SHA-256 hashing. Ignore the root $schema hint;
  preserve array order and hash before inserting defaults. Reject duplicate JSON
  keys, non-finite constants, unknown fields/references, duplicate codes/members,
  role overlap, and upstream_id without provenance.
- [x] Move the canonical JSON Schema into packaged data. Validate the bundle with
  jsonschema in tests, including paired invalid-shape cases and en/de coverage.
- [x] Simplify the models and replace the unapplied catalog migration.
- [x] Implement reconciliation with stable UUIDs, exact role/group sets, unused
  muscle creation, complete group deletion, and a read-only dry-run.
- [x] Replace the old RepDB CLI: default bundle or --input; --force and --dry-run.
  Validate before DB access, then acquire pg_advisory_xact_lock(74823391012), read
  checkpoint, reconcile, update checkpoint, and commit once. Matching hash and
  SYNC_VERSION skip a normal run, including explicit input. Dry-run always runs.
  Roll back on failure. Remove downloads and runtime translation publication.
- [x] Add startup sync immediately after alembic upgrade head; failure aborts via
  set -e. Preserve admin setup, RLS guard, and exec uvicorn.
- [x] Update importer/format/data documentation and remove unused direct httpx2.
- [x] Finish static checks, full suite, wheel resource inspection, and one fresh
  read-only code review. Record actual results in the handoff/final response.

## Review focus

1. Invalid later input must fail before DB access even with a matching checkpoint.
2. Commit failures preserve both catalog rows and checkpoint. Lock release and two
   competing starts must work with real PostgreSQL sessions.
3. Dry-run leaves the Session, data, checkpoint, and locale files unchanged.
4. Role and activation changes preserve exercise IDs. Group updates preserve
   retained IDs, clear empty sets, permit overlaps, and delete omitted groups.
5. Packaged defaults work outside repository CWD without upstream access or
   writable translation files. Wheel includes catalog, schema, license, locales.
6. The new revision contains only the catalog tables and preserves restrictive
   links. This is a fresh migration for an unapplied development branch.

## Validation

Run changed-file Ruff, format, and ty checks, plus the complete pytest suite using
the configured test services. Compare any pre-existing type failures against HEAD
rather than expanding this change into unrelated fixture repairs. Build a wheel
outside the repository and inspect packaged assets. Do not run a separate migration
execution test or change production schemas.

## Verified result

- Full suite: 845 passed in 220.71 seconds.
- Changed-file Ruff and format checks passed; git diff --check and bash syntax passed.
- Type checking has no new errors. Three existing errors in tests/conftest.py were
  reproduced against HEAD (PyTrack extensions, timezone assignment, locale assignment).
- Wheel contains catalog, schema, source license, and en/de labels. jsonschema is
  absent from production requirements.
- Fresh review found one global-checkpoint switching bug. Its regression test
  failed before the fix and passed after it; full suite passed after the fix.
- Native enum mapping and migration reviewed; migration execution explicitly
  waived by the user. Validation completed before committing.
