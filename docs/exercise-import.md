# RepDB exercise import

Run against a database with catalog tables already prepared (the catalog migration
is deferred):

```sh
ENVIRONMENT=testing uv run python -m verve_backend.cli.import_exercises \
  --translations-dir ./exercise-names
```

The Click command resolves upstream HEAD once and pins the httpx2 download to that
commit. A matching completed checkpoint and verified `repdb-import.json` manifest
skip the snapshot download and leave files unchanged. Use `--force` to reimport,
or `--dry-run` to validate and report changes without database or file writes.

For offline input, supply `--input exercises.json --revision <full-commit-sha>`.
Local input always runs validation/import and never makes network requests.

Imports preserve existing UUIDs, application codes, activation flags, absent
exercises, unused muscles, and groups. Global code collisions fail; in particular,
the shared test seed's non-RepDB `squat` conflicts with the full RepDB snapshot.
Use an isolated test schema for full-snapshot smoke testing.

English/German names merge into `en.json` and `de.json`, preserving unrelated
sections, absent keys, and existing German names when the source lacks them.
A session advisory lock serializes RepDB runs through publication. Catalog data
and checkpoint invalidation commit together; publication follows, then the
checkpoint is marked complete. If publication fails after commit, the command
reports this and exits unsuccessfully; rerun to repair the output.

Source and license/attribution: <https://github.com/RepDB/exercise-dataset>.
Runtime localization, migrations, group maintenance, and API/UI work are deferred.
