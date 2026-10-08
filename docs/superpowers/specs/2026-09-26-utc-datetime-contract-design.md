# UTC Datetime Contract

This is the original design proposal. For current behavior, see
[How timezones work in the backend](../../activity-timezone.md). The backend now
uses the user's saved timezone for calendars and accepts offsetless activity
input using the selected activity timezone.

## Goal

Make timestamp handling consistent with SQLModel 0.0.46: application instants are
aware UTC values, while calendar views group those instants in the timezone provided
by the frontend.

## Contract

- Generate server timestamps as aware UTC values, using `datetime.now(UTC)`.
- Require an explicit timezone offset on external datetime inputs. Reject naive
  timestamps rather than guessing their meaning from the server timezone.
- Normalize aware external timestamps to UTC before application processing and
  persistence.
- For user-entered local date/time values, the frontend uses the user's IANA timezone
  to resolve the selected wall-clock time and sends the resulting offset-aware instant.
  The backend rejects an unresolved naive value, then normalizes the instant to UTC.
- Generate audit timestamps such as `created_at`, `updated_at`, and token expiry from
  the server clock in UTC. These describe instants and do not use the user's timezone.
- Pass an IANA timezone name in the `timezone` query parameter from the frontend to
  date-bucketed activity views. Validate it as a `ZoneInfo` timezone and return 422
  for invalid names. Use UTC when callers omit it during rollout.
- Convert UTC instants to the requested timezone only when calculating calendar
  dates or displaying local time. Keep duration arithmetic and stored instants in UTC.
- Test fixture datetimes that are written to timestamp columns can remain readable
  local wall-clock values, but tests must attach the system timezone explicitly.
- Record these rules in `AGENTS.md` so future changes follow the same contract.

## Scope

Apply the contract to model timestamp defaults, API datetime schemas, activity import
schemas and conversion, and server-generated timestamps in routes and domain logic.
Use the frontend timezone for calendar, week, and activity-grid date boundaries and
database date buckets. Review other date-based activity aggregations and filters for
the same timezone dependence.

Do not change the production database schema or migrate existing production data in
this phase. That migration remains a separate follow-up after application behavior and
tests are stable.

## Validation

- Add focused tests for rejecting naive external timestamps and normalizing offset
  timestamps to UTC.
- Test calendar and activity date buckets in a non-UTC timezone, including a UTC
  instant that falls on a different local date.
- Run the affected route and import tests, then the full test suite.
- Run Ruff check and format validation.
