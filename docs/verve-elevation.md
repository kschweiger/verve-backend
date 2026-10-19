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

## Docker images

Images bundle the same verified grid at
`/opt/verve/proj/us_nga_egm08_25.tif`, selected by the image's
`VERVE_EGM2008_GRID` default. The root-owned file is readable by the normal
`verve` user (UID/GID 1000). Builds validate a real conversion under this user
with networking disabled. Startup and requests never install or download grids.

Host `data/proj/` files are excluded from the build context. The grid-installation
stage uses a BuildKit cache at `/var/cache/verve-egm2008`: a checksum-valid cached
grid is reused when the layer rebuilds, while a missing or invalid cached grid
is downloaded using the existing checksum-verifying downloader. Download or
validation failures abort the build. Only the verified artifact is copied into
the runtime image; the cache mount is not part of that image.

Build and verify locally for each architecture:

```bash
docker buildx build --platform linux/arm64 --load -t verve-wp7:arm64 .
python scripts/verify_docker_elevation.py verve-wp7:arm64 --platform linux/arm64
docker buildx build --platform linux/amd64 --load -t verve-wp7:amd64 .
python scripts/verify_docker_elevation.py verve-wp7:amd64 --platform linux/amd64
```

Cross-architecture execution requires Docker emulation support. The verifier
requires only host Python and Docker; it does not pull or push images. It checks
the packaged checksum, runtime user, architecture, known conversion, ASGI startup
and valid/missing/corrupt/unreadable overrides with `--network none`.

To override the bundled grid, bind-mount a file read-only and set
`VERVE_EGM2008_GRID` to its container path. It must have the pinned checksum above;
UID 1000 needs read permission and search permission on its parent directories.
Missing, corrupt or unreadable overrides fail startup rather than falling back
to the bundled file.

The offline verifier invokes the existing ASGI lifespan directly. Normal container
startup still waits for PostgreSQL, runs migrations, verifies RLS and requires the
existing application/service configuration. WP7 leaves CI and the release
procedure unchanged.

## Existing activities and release deployment

Earlier Verve imports may contain unconverted file heights. Use the existing
explicit activity reprocessing operation to rebuild those activities from their
original Verve source. WP3 does not run a bulk rewrite or change database schema
or storage semantics.

Container packaging and local architecture verification are tracked in
[WP7 — Docker elevation grid deployment](superpowers/plans/2026-10-19-geojson-wp7-docker-elevation.md).
The grid startup requirement remains mandatory for every deployment.

Broader Verve export support remains a separate follow-up. WP3 changes elevation
conversion for the existing spatial exporter only.
