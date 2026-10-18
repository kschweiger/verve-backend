# Verve file elevations

Elevation conversion applies exclusively to validated Verve 1.0 files. FIT,
GPX, non-Verve GeoJSON, and generic track attachment retain their existing
behavior. A `.json` extension alone does not activate conversion.

Internal storage remains sea-level height in meters. Verve files contain height
above or below the WGS 84 ellipsoid. The EGM2008 grid provides the location-specific
geoid offset `N`:

- Import: stored height = file height − `N`.
- Export: file height = stored height + `N`.

Import converts before calculating missing summaries or storing points. Supplied
ascent/descent summaries remain authoritative, including zero. Export does not
modify database values. Reprocessing starts from the original stored Verve bytes
each time, so conversions do not accumulate.

## Required local grid

Install before starting the backend or running tests:

```bash
uv run python -m verve_backend.cli.download_elevation_grid
```

The default destination is `data/proj/us_nga_egm08_25.tif`. Set
`VERVE_EGM2008_GRID` to select another file path; use the same setting for
installation and the application.

- Source: <https://cdn.proj.org/us_nga_egm08_25.tif>
- SHA-256: `4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a`
- Model: NGA EGM2008, worldwide 2.5-minute geoid grid, public domain.

The downloader checks the checksum before atomically replacing the destination.
Failed or interrupted downloads preserve an existing installation. The application
checks the grid at startup and aborts with an explicit error if it is missing,
corrupt, or unreadable. Conversion uses the required local grid with no network,
optional-grid, or identity fallback. Tests require installation and do not skip
real-grid coverage. CI installs the same pinned artifact before pytest.

## Existing activities and release deployment

Earlier Verve imports may contain unconverted file heights. Use the existing
explicit activity reprocessing operation to rebuild those activities from their
original Verve source. WP3 does not run a bulk rewrite or change database schema
or storage semantics.

Dockerfile changes, runtime-image installation, offline image verification, and
release-architecture checks are deferred to WP6. The grid startup requirement is
already mandatory; release images must satisfy it before deployment.

Broader Verve export support remains a separate follow-up. WP3 changes elevation
conversion for the existing spatial exporter only.
