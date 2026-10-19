# Activity timezone fixtures

Copy this entire folder to reuse these files in another client. No Python code or generation step is required.

The backend publishes a SHA-256 digest at `tests/resources/timezones.sha256` and
a reproducible ZIP at `tests/resources/timezones.zip`. The digest covers every
file in this folder using sorted relative paths and file bytes. A frontend sync
script can compare its saved digest with the published digest, download the ZIP
when they differ, replace its fixture copy, and save the new digest. A digest
change is a cue to review frontend behavior against the updated scenarios.

For the `main` branch, the raw download URLs are:

- Digest: `https://raw.githubusercontent.com/kschweiger/verve-backend/main/tests/resources/timezones.sha256`
- Archive: `https://raw.githubusercontent.com/kschweiger/verve-backend/main/tests/resources/timezones.zip`

After changing fixtures, regenerate the published files with
`python scripts/timezone_fixtures.py --write`. Check them with
`python scripts/timezone_fixtures.py --check`; pre-commit runs the same check.

`cases.json` gives each scenario's user timezone, optional request override, upload routes, and expected activity/track instants. `expected.local_start` is the local time a frontend should display using `expected.timezone`; it is not a timestamp to send to the API.

All tracks contain three points, five minutes apart, with heart rates of 96, 108, and 120 bpm. Expected heart rates and elapsed seconds are in the manifest, aligned with `point_times`, so clients can check plot values and their positions. GPX uses a `heartrate` extension; Verve uses `heartRates`.

Berlin and Los Angeles coordinates are real locations; tracks are synthetic. GPX files ending in `local` have no timestamp offset and exercise application fallback. `offset` uses a numeric offset, and `utc` uses `Z`. Every Verve timestamp has an explicit offset; only Verve JSON can declare an IANA timezone in `properties.timezone`.

Verve timestamp offsets determine instants independently of display context. The declared New York example uses `-04:00`, the Berlin example without a recorded zone uses `+02:00`, and the non-spatial owner-fallback example uses `-07:00`. A Tokyo request override displays the New York example at 23:00 while preserving its 14:00 UTC start and sample instants. A named timezone never supplies a missing offset in a Verve file.

The scenarios cover summer/winter offsets, travel, the daylight saving clock change, file/request precedence, owner fallback without geometry, and preservation of aware instants. The request-override case deliberately reuses the declared-zone file with different request settings.

Backend integration tests also use these files for export/import and display-zone correction, checking that timestamps and heart rates are preserved. The fixtures exclude ambiguous offsetless times during the clock change: that file uses explicit offsets.

Run the backend tests with `uv run pytest tests/routes/test_timezone_files.py` using the repository's test services.

## Inspecting the test database

These tests reuse two seeded users, both with password `12345678`:

| User | Email | Saved timezone |
| --- | --- | --- |
| `username3` | `user3@mail.com` | `America/Los_Angeles` |
| `username4` | `user4@mail.com` | `Europe/Berlin` |

Users and uploaded activities remain after the run. Activity names begin with `Timezone:` and identify the scenario and upload route. The correction example is named `corrected-zone`; round-trip examples are named `roundtrip-source`.

The existing suite rebuilds the test database at the start of each pytest session, so inspection reflects the latest run. To load just this fixture collection, use the command above. The folder itself contains no login credentials or Python dependencies in its upload files or manifest; frontend consumers can use their own accounts with the indicated settings.
