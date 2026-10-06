# How activity timezones work

The backend keeps two pieces of information: **when an activity happened**
and **which timezone to use when displaying it**. This lets a hike in Los
Angeles show its local start time even when its owner lives in Berlin.
Activity start and track point timestamps are stored as instants; the saved
display timezone is separate from those timestamps.

## Timestamp, offset, and timezone

A timestamp such as `2026-08-10T16:00:00Z` identifies a moment in UTC.
The same moment can be written as `2026-08-10T09:00:00-07:00`.
The `-07:00` is an offset: a difference from UTC.

A timezone name such as `America/Los_Angeles` contains the rules for choosing
that offset on a particular date, including daylight saving time. Similarly,
`Europe/Berlin` uses UTC+1 in January and UTC+2 in August. The activity's date
determines the offset, even if you view it in a different season.

## When an activity is uploaded

The backend chooses one display timezone for the whole activity, using the
first available source:

1. An explicit `timezone_name` in the request.
2. A timezone saved in a Verve file's `properties.timezone`.
3. The timezone at the first timed GPS point with real coordinates.
4. The owner's saved timezone.

If GPS lookup cannot identify a land timezone, the backend uses the fallback.
The first timed GPS point's zone applies even if the track later crosses into
another timezone.

Times containing `Z` or an explicit offset keep their meaning. FIT timestamps
are decoded as UTC. GPX and GeoJSON times without an offset are interpreted
in the selected activity timezone.

Manual activities use the request override or the owner's timezone. Replacing
a track uses the override or GPS timezone; otherwise it keeps the saved zone.
Users can correct an activity's timezone without changing existing timestamps.
Verve export and import preserve the saved timezone.

## What the frontend receives

For a Los Angeles hike starting at 09:00 in August:

```json
{
  "start": "2026-08-10T16:00:00Z",
  "timezone": "America/Los_Angeles"
}
```

Activity detail and list responses include `timezone`; track point timestamps
remain instants. To display local times, the frontend must format them using
the activity's timezone, for example with `Intl.DateTimeFormat`. This displays
09:00 and handles daylight saving automatically. Formatting happens when a
time is displayed; it does not require rewriting every track point or manually
adding an offset.

The owner's timezone still determines existing calendar filters and goals.
