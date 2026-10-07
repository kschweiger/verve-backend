# How timezones work in the backend

The backend separates **when something happened**, **the activity's local time**,
and **the user's calendar**.

| Value | Meaning | Example |
| --- | --- | --- |
| Timestamp | A moment in time, handled as an aware UTC value | `2026-08-10T16:00:00Z` |
| Activity timezone | The saved zone for displaying this activity | `America/Los_Angeles` |
| User timezone | The saved zone for calendars, filters, statistics, and goals | `Europe/Berlin` |

The user's timezone defaults to `Europe/Berlin`. It is returned by
`GET /users/me/settings` and changed through `PATCH /users/me/timezone`.

## Offsets and daylight saving time

`16:00Z` and `09:00-07:00` describe the same moment. The `-07:00` is an
**offset** from UTC. A **timezone** such as `Europe/Berlin` supplies the rules
for choosing the offset: UTC+1 in January, UTC+2 in August. The timestamp's
date determines the offset, even if you view it in a different season.

## When an activity is uploaded

The backend chooses one display timezone for the whole activity, using the
first available source:

1. An explicit `timezone_name` in the request.
2. A timezone saved in a Verve file's `properties.timezone`.
3. The timezone at the first timed GPS point with real coordinates.
4. The owner's saved timezone.

GPS lookup uses local timezone data. Ocean or unusable coordinates fall back
to the owner's zone. A track crossing timezone boundaries keeps its first zone.

Times with `Z` or an offset keep their meaning. FIT times are decoded as UTC.
Offsetless GPX/GeoJSON times are interpreted in the selected activity zone.
Swimming lap/set times follow the same rule; other metadata is left as supplied.
Raw uploaded files remain unchanged.

Manual activities use the request override or the owner's timezone. Replacing
a track uses the override or GPS timezone; otherwise it keeps the saved zone.
Users can correct an activity's timezone without changing existing timestamps.
Verve export and import preserve the saved timezone.

## Storage and API responses

Activity starts, track times, audit timestamps, and token expiry are instants,
handled as aware UTC values. Responses include `Z` or an offset; the activity's
zone is separate. Durations measure elapsed time. Equipment purchase dates
are dates such as `2026-08-10`, with no timezone.

For a Los Angeles hike starting at 09:00 in August:

```json
{
  "start": "2026-08-10T16:00:00Z",
  "timezone": "America/Los_Angeles"
}
```

Activity detail and lists include `timezone`. The frontend formats timestamps
using that zone, for example with `Intl.DateTimeFormat`, to show 09:00 above.
It formats labels as needed; it needn't rewrite the track or manually add offsets.

## Calendars, statistics, and goals

These use the **user's saved timezone**, including when travelling. A hike at
23:30 on August 10 in Los Angeles displays that time, but belongs to August 11
in a Berlin user's calendar: it is already 08:30 there. Grouping uses the
activity's start, without splitting it across days.

Local day/week/month/year boundaries are converted to UTC for queries, including
the beginning and excluding the end. This handles 23- and 25-hour days.
Calendar grids, streaks, period filters, and goal progress follow this rule.
Yearly highlights use the user's timezone when calculated.

Changing the user's zone leaves activity instants and display zones unchanged.
Calendar requests use the new setting; goals recalculate when fetched.
Stored yearly highlights need recalculation to reflect the change.

## Database migration

Alembic revision `d9e3386babd7` adds the required activity and user timezone
columns, fills existing rows with `Europe/Berlin`, and converts timestamp columns
to `TIMESTAMP WITH TIME ZONE`. The temporary database defaults used to fill those
rows are removed; new writes use the application's timezone selection.

Existing offsetless timestamps are interpreted as **Europe/Berlin wall times**.
The conversion explicitly uses that zone, independently of the database session:
12:00 in January becomes 11:00Z, while 12:00 in July becomes 10:00Z. Downgrading
converts instants back to Berlin wall times.

Equipment purchase timestamps become `DATE`, preserving the recorded calendar
date. This discards their time of day; downgrading restores midnight.

Historical file reprocessing, activity timezone corrections, JSON metadata
conversion, and rebuilding derived data remain a separate data migration.

## Current limits

Offsetless times around a daylight saving clock change can be ambiguous or
nonexistent. These aren't currently rejected; use explicit offsets to identify
the intended instant.

Application tests build their schema directly from the models. Migration tests
exercise this revision against temporary legacy tables in PostgreSQL.
