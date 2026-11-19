# Bundled exercise catalog sync

The command reads packaged catalog data without network access or file writes.
Names remain in the packaged English/German locale JSON files.

```sh
python -m verve_backend.cli.import_exercises
python -m verve_backend.cli.import_exercises --dry-run
python -m verve_backend.cli.import_exercises --force
python -m verve_backend.cli.import_exercises --input /path/catalog.json --dry-run
```

The database tables must already exist. The container's `run.sh` runs Alembic,
then syncs the catalog before admin setup, RLS verification, and Uvicorn. A sync
failure stops startup. The command itself never creates or migrates tables.

Input is validated before opening the database. Exercises and muscles match by
stable code and keep their UUIDs. Included exercises get exactly the declared
muscle roles and activation flag; omitted `is_active` means `true`. Retire an
exercise explicitly with `is_active: false`. Omitted exercises, their assignments,
and unused muscles remain stored.

All display groups and memberships follow the input. Retained group codes keep
their UUIDs; changed or empty member sets replace existing sets. Omitted groups
and their memberships are deleted. These are application display groups, not
user-maintained data.

A PostgreSQL transaction advisory lock serializes starts, including checkpoint
lookup. Catalog changes and `ExerciseCatalogSyncState` commit together. Failure
rolls back both and releases the lock.

The checkpoint stores catalog code, content hash, and importer behavior version.
Only the currently applied catalog retains a checkpoint, because display groups
are global. Applying a different catalog invalidates the previous checkpoint.
A matching hash and version skip a normal sync, including explicit `--input`.
Hashing excludes the root `$schema` editor hint and locale files. See the
[format contract](exercise-catalog-format.md) for canonicalization details.
Increment `SYNC_VERSION` when sync behavior changes and the same data must run
again. `--force` bypasses the checkpoint to repair database edits. `--dry-run`
always previews current differences and writes neither data nor checkpoint.
A checkpoint records a successful sync; it does not detect later database drift.

Success prints JSON with `status` (`imported`, `unchanged`, or `dry_run`),
`catalog_code`, and `content_hash`. Applied/preview runs also report counters and
warnings. Invalid input or database failures exit nonzero. The former
`--revision` and `--translations-dir` options are removed.

The catalog and license are bundled in the application image. Runtime validation
uses Pydantic; JSON Schema validation and locale coverage run in tests. Builds do
not download upstream data. An older image contains an older catalog, which a
sync can reapply; coordinate rollbacks and avoid mixed catalog versions.

See the [curation and source notes](../verve_backend/data/README.md). API endpoints,
workout logging, body-map rendering, and runtime localization remain separate work.

## Importer tests

The configured test database must contain the `catalog_import_tests` schema in
addition to the application's `api` schema. CI creates both before pytest. For a
local test database, create the additional schema once with the test database
owner:

```sql
CREATE SCHEMA IF NOT EXISTS catalog_import_tests;
```

The importer test module overrides the shared database fixture. It creates only
the six catalog tables in this schema and clears their rows before and after each
test. Its CLI calls use real sessions and commits against the isolated tables.
The fixtures leave the schema itself in place and do not reset or restore the
application catalog. Each test supplies any existing catalog data it needs.
