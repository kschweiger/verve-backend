# Verve GeoJSON 1.0 backend behavior

Authority: `backend-release-changes.md`, the [release work packages](superpowers/plans/2026-10-17-geojson-release-work-packages.md), and the sibling geojson-flavor repository's core/swimming 1.0 specifications. This page describes the supported backend subset and application compatibility, rather than claiming complete format conformance.

## Import and timestamps

`POST /activity/import/` and recognized Verve uploads to `POST /activity/auto/` use the canonical validated import path. Paths are relative to the configured API prefix. Spatial, non-spatial sensor-series, and summary-only activities are supported; original source bytes remain unchanged in object storage for explicit reprocessing.

Every feature requires geometry and timestamps. Spatial LineStrings need at least two three-number positions. Non-spatial features use explicit `geometry: null`; summary-only features use `coordTimes: []`. Geometry modes cannot be mixed. Supplied sensor arrays must align with timestamps; missing sensor positions and reported zeros remain in place.

`startTime` and every sample timestamp require `Z` or a numeric UTC offset. Offsetless Verve timestamps return HTTP 422 even when a named timezone is provided. Request overrides, recorded zones, GPS inference, and owner fallback select display context without reinterpreting aware instants. Manual activities, GPX, generic GeoJSON, and application swimming metadata retain their existing application timezone fallback.

The importer retains existing Pydantic aliases, defaulted generator, and numeric coercion compatibility. Portable fixtures use canonical names and explicit generators. Fractional power samples are rejected because storage uses integers. Import acceptance alone is not proof of strict file-format conformance.

## Units, summaries and metadata

File speed summaries use m/s; stored activity summaries use km/h: 10 m/s stores as 36 km/h and serializes back as 10 m/s. Supported supplied summaries remain authoritative, including zeros and partial/empty summaries. Wholly absent or null metric summaries are calculated when usable samples exist. Energy stays in kcal; distance converts between file meters and stored kilometers.

Cadence is nullable fractional RPM in storage. Running Verve input counts both feet: 171 steps/min stores as 85.5 RPM. Running track, collection, and segment responses return steps/min using the current stored activity classification. Clients must remove their own doubling. Cycling RPM is unchanged; other sports retain source counts such as swimming/rowing strokes. FIT/GPX parser values retain their existing RPM compatibility convention. See [cadence behavior and deployment](verve-cadence.md).

Cadence summaries and metric minima lack dedicated activity storage. Source bytes retain supplied values, but activity statistics and export cannot promise to reconstruct them.

Recognized swimming 1.0 envelopes are validated directly. Fractional measurements, scalar zeros, counts without details, and details without counts are supported. Invalid counts, indices, references, wire timestamps, and empty-only metadata fail. Duration is elapsed interval time; rest is separate and length SWOLF uses length duration plus strokes. Arbitrary other metadata remains supported. See the [swimming contract](product-specs/verve-swimming-metadata.md) for wire versus backend representations.

## Elevation and export

Storage remains sea-level meters. Validated Verve import subtracts the location-specific EGM2008 offset; spatial serialization adds it back. Conversion precedes calculated statistics and writes. Reprocessing starts from original bytes to prevent accumulated conversion. FIT, GPX, generic GeoJSON, and generic attachments retain existing elevation behavior. Historical datum assumptions require source review. See [elevation and the required grid](verve-elevation.md).

There is no public Verve export endpoint. The internal spatial serializer is tested for supported summaries, elevation, cadence, swimming metadata, and public-route reimports. Public export, non-spatial/summary-only database export, broader sensor serialization, and summary storage expansion remain deferred. Zero-only heart-rate/power arrays and temperature export are not covered by the current serializer's preservation guarantees. Null-geometry model serialization does not establish database exporter support.

## Release deployment

1. Apply the user-generated cadence integer-to-float migration, preserving existing values and RLS policies. Model-created pytest tables do not prove upgrade compatibility.
2. Require WP7's verified grid-bearing images for `linux/amd64` and `linux/arm64`, including offline runtime-user conversion. Missing, corrupt, or unreadable grids already abort startup.
3. Coordinate running cadence responses with clients.
4. Review historical Verve sources and explicitly reprocess eligible activities through [admin maintenance](admin-maintenance.md). No automatic rewrite or blanket historical cadence division is performed.

Current checks and unresolved release gates are recorded in the [WP6 verification report](superpowers/plans/2026-10-19-geojson-wp6-release-verification.md).
