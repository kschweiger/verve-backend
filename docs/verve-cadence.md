# Cadence storage and conversion

The database always stores cadence in **revolutions per minute (RPM)** using the
cycling convention, independent of the activity type. `TrackPoint.cadence` is a
nullable float. Activity-specific units are applied at import and output
boundaries, never by changing the meaning of the stored column.

For example, a running Verve file reporting 171 steps/min stores 85.5 RPM. The
backend returns 171 steps/min for that running activity. A cycling activity with
85.5 RPM in storage returns 85.5 RPM.

## Import

Verve running cadence counts both feet. Import divides these samples by two
before statistics or database writes. Source activity type/subtype determines
the input units, even when the request overrides the stored activity type.
The validated source model, supplied summaries, and original file bytes are
preserved. Reprocessing reads those original bytes and applies conversion once.

Running means `Foot Sports` with subtype `Run`, `Trail Run`, or `Treadmill`.
Other subtypes, including `Walk`, and missing subtypes receive no scaling.
Cycling and other sports' Verve cadence values are retained without scaling.

FIT and supported GPX cadence retain the values provided by geo-track-analyzer.
The locked Garmin FIT SDK uses RPM for base cadence and strides/min for running
cadence summaries. GPX has no universal core cadence unit; accepting supported
GPX cadence as RPM is a compatibility assumption. No value-range heuristics or
producer detection are used.

References: [Garmin FIT SDK profile](https://github.com/garmin/fit-python-sdk/blob/main/garmin_fit_sdk/profile.py)
and [GPX 1.1 schema](https://www.topografix.com/GPX/1/1/).

## API responses and Verve export

The backend uses the current stored activity type/subtype when returning cadence:

- Running: multiply RPM by two to return total steps/min.
- Cycling: return RPM unchanged.
- Other sports: return the reported counts/min without additional scaling.

This applies to track samples, collection samples, and segment minimum, average,
and maximum cadence. SQL aggregation continues using stored RPM. Clients must
not multiply running cadence again. Changing an activity's type changes its
response interpretation without rewriting stored cadence.

API responses preserve fractional precision. Verve 1.0 requires integer samples,
so export converts units and then uses Python's `round()` (nearest integer, ties
to even). Thus running 85.5 RPM exports as 171 steps/min, while cycling 85.5 RPM
exports as 86 RPM. Export does not modify storage. Null positions and reported
zeros survive; wholly unavailable cadence arrays may be omitted.

## Limits and deployment

Activity-level cadence summaries have no database columns. `stats.cadence` remains
accepted and preserved in the original source bytes, but it is not persisted as
activity statistics or synthesized on export. Non-spatial and summary-only
export support remains a separate follow-up.

The locked parser does not expose nested Garmin GPX
`TrackPointExtension/cad` as cadence, and FIT's `fractional_cadence` remains a
separate extension rather than being combined with base cadence. These are
geo-track-analyzer follow-ups; this backend adds no adapters for them. Other
sports retain their source's counted motion, such as swimming/rowing strokes.

The user generates the cadence integer-to-float migration from the final model.
Apply it before deploying this code. The schema migration must preserve existing
numeric values and row-level security policies.

Earlier running Verve imports stored steps/min directly. Reprocess those
activities from their original source files before relying on the new response
or export semantics. Do not bulk-divide historical rows: FIT/GPX values use the
existing RPM convention. Deploy clients without any previous running cadence
multiplication alongside the backend response change.
