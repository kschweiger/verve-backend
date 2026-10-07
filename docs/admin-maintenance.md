# Admin maintenance jobs

These routes require an authenticated admin and run through the existing Celery
worker. Paths below are relative to the API prefix (normally `/api/v1`). Both POST
routes accept an optional `user_id` query parameter; omit it to select all users.

## Recalculate highlights

`POST /admin/recalculate-highlights` returns HTTP 202 and a `users` array containing
each selected user's `user_id` and `task_id`.

Each task recalculates all lifetime and yearly rankings from that user's current
activities and track points, including activities without a stored source file.
Previous rankings are replaced in one transaction. If a calculator fails, the
previous rankings remain and the task fails. Repeated recalculation produces the
same rankings without duplicate entries.

The existing `/admin/recalculat_hightlights` spelling remains as a deprecated HTTP
204 alias that queues the same work.

## Reprocess stored tracks

`POST /admin/reprocess-tracks` returns HTTP 202 with two arrays:

- `tracks`: an `activity_id`, `user_id`, and `task_id` for every selected stored track.
- `users`: a `user_id` and completion `task_id` for every affected user.

Selection uses the database's `raw_track_data` records. Each activity gets its own
background task, which downloads the existing S3 object and parses it with the
installed geo-track-analyzer. The original object and source mapping are preserved.

The rebuild replaces track points, geometry, sensor values, and extensions;
updates distance, duration, elevation changes, and available speed, power, and
heart-rate summaries; and resolves timestamps and the activity timezone using the
normal import rules. Renamed FIT extensions therefore come from the current
parser, including `raw_distance_m` and `enhanced_speed_ms`. Extensions previously
cleared from the database can be restored from the original file.

Activity identity, names, types, metadata, creation times, equipment, tags, and
other links are preserved. Cached automatic goal progress is invalidated for
recalculation; manual goal progress is preserved.

Raw segment boundaries are regenerated. Existing cuts are matched by their old
point timestamps, retaining the old point index when it still matches or using a
unique matching timestamp. Unresolved or duplicate cuts are removed; sets with
no remaining cuts are removed. These removals do not discard the rebuilt data.
Set names are editable, so resolvable sets are preserved regardless of their
names. An existing `Raw track segments` set is reused when its cuts match the
current source boundaries; otherwise those boundaries get a separate set.

Parsing, download, and database failures leave that activity's previous data
unchanged. Other activity jobs continue. Once all selected tracks for a user
finish, a completion task invokes the same highlight recalculation used by the
standalone endpoint, provided at least one track was successfully rebuilt.
Highlight errors do not undo committed track rebuilds; the standalone route can
retry the rankings separately.

## Job status

`GET /admin/tasks/{task_id}` returns `task_id`, Celery `state`, `result`, and `error`.
Pending or running jobs have no result. Unknown or expired IDs appear as `PENDING`.
Result retention follows the existing Celery result backend configuration.

An activity task returns `activity_id`, `user_id`, `number_of_points`,
`removed_cuts`, and `error`. A handled activity failure has Celery state `SUCCESS`
with a non-null result `error`, allowing the other jobs and completion task to run.
Check this field when inspecting individual activity jobs.

A user's track completion result reports `reprocessed`, `failed`, `removed_cuts`,
`highlights_rebuilt`, and the individual `tracks` results. A standalone highlight
task reports `activities` and `highlights_rebuilt`.

Run the timezone schema migration before these jobs. Workers need the configured
database, S3 store, Redis broker, and Redis result backend; per-user completion
uses a Celery chord. Reprocessing is separate from Alembic and only runs when an
admin invokes the route.
