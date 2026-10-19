# WP7 — Docker elevation grid implementation and verification

Requirements: [release checklist](../../../backend-release-changes.md) and
[work-package outline](2026-10-17-geojson-release-work-packages.md).

## Approved scope

- Package WP3's checksum-pinned EGM2008 grid in the runtime image.
- Reuse the existing downloader, converter and mandatory ASGI startup validation.
- Exclude host `data/proj/`; retain a checksum-verified BuildKit download cache.
- Verify both `linux/amd64` and `linux/arm64` images locally without network.
- Leave all CI workflows, release jobs, tags, publishing and deployment unchanged.
- No storage changes, migrations, conversion changes or image pushes.

## Implementation plan

- [x] Task 1: add a cached grid-installation stage and runtime-user build validation.
- [x] Task 2: verify packaged checksums, conversions, startup and overrides offline.
- [x] Task 3: document deployment requirements and record local acceptance evidence.

Runtime default: `/opt/verve/proj/us_nga_egm08_25.tif`, selected through
`VERVE_EGM2008_GRID`. Files are root-owned and readable by `verve` (UID/GID 1000).
The BuildKit cache is `/var/cache/verve-egm2008`; only checksum-valid files are
reused, and the final artifact is copied outside the cache before runtime copying.

Verification command:

```bash
python scripts/verify_docker_elevation.py IMAGE --platform linux/arm64
python scripts/verify_docker_elevation.py IMAGE --platform linux/amd64
```

## Execution record

Ruling: retain the existing feature checkout and unrelated working-tree files —
this continues WP1–WP6 on `refactor/geojson-final`; a new checkout would lose the
established local context. No branch integration is included. The user authorized
a WP7 commit after implementation and validation.

Pre-flight: Task 1 produces the grid path and default user consumed by Task 2;
Task 3 records their observed results. The agreed interfaces match.

Ruling: keep all build logic in `verve_backend.cli.install_elevation_grid` —
the user explicitly rejected inline Python in the Dockerfile. Docker instructions
only invoke module commands; the existing downloader remains unchanged.

RED: the baseline ARM64 image built successfully after excluding host grids,
but its converter raised `ElevationConversionError: Required EGM2008 grid missing`.
The offline verifier also rejected its missing configured image grid path.
All four installer test cases failed before the new module existed.

GREEN: both local images built successfully, including the network-disabled
runtime-user control-point check. All five offline verifier scenarios passed on
each architecture. Focused tests: 23 passed. Final full suite: 722 passed, 307 warnings
in 163.72 seconds. Ruff lint, formatting and ty passed for the three new Python
files. The existing warning categories are unchanged from WP6.

An explicit `--no-cache-filter elevation-grid` probe exposed an empty cache mount.
The next diagnostic build downloaded the artifact again and observed it in the
mount. Changing just the installation instruction to `RUN --network=none` in a
temporary Dockerfile then reran the layer and reused the verified cache offline.
An empty or pruned cache requires a new download; that is separate from ordinary
layer invalidation.

Review: no Critical or Important production findings. The test fixture now copies
the configured grid instead of hardlinking it, so an installation on another
filesystem works too. Ruling: treat this portability finding as a required test
correction — arbitrary configured grid paths must remain usable across mounts;
the extra test-fixture copy is the cost.

The reviewer set aside the then-pending local acceptance probes; their successful
results below now supply the missing evidence. Full entrypoint startup against
services remains outside this packaging check: normal PostgreSQL/migration/RLS
requirements are unchanged, and the verifier tests the real ASGI lifespan only.

## Local image evidence

Docker Engine 29.8.2 / BuildKit 0.33.1 on ARM64 Docker Desktop; AMD64 ran with the
existing Docker emulation. No images were pushed and no workflows were changed.

| Image | Local image ID | Result |
| --- | --- | --- |
| `verve-wp7:arm64` | `sha256:950563b96cc3122c171193df48bbe99a4497c8159cbc44bca854ae3b8cb348b1` | Build and five offline checks passed |
| `verve-wp7:amd64` | `sha256:d42210a340f037ddf549d5cc1df9ae93b97c0387cff139d20f55b3526c3492c4` | Build and five offline checks passed |

Both images reported the expected architecture, user `verve` / UID/GID 1000,
the configured runtime path and SHA-256
`4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a`.
The grid converted `(11.5, 48, 100)` to `53.980892181396484` sea-level meters and
back to 100 ellipsoidal meters. All five scenarios ran with `--network none`:
default and alternate-path startup succeeded, and missing/corrupt/unreadable
overrides failed even after priming the converter cache.

| Additional local probe | Observed result |
| --- | --- |
| Initial grid-stage build | Downloaded and verified the pinned artifact |
| Second architecture build | Reused the checksum-verified shared cache |
| Changed grid installation instruction, network disabled | Reused cached grid; successful runtime build |
| Unverified host sentinel inside ignored `data/proj/` during that build | `/app/data/proj/` absent; all five offline checks passed |
| Temporary Dockerfile removes installed artifact | Build exit 1 at runtime `COPY`, artifact not found |
| Temporary Dockerfile corrupts installed artifact | Build exit 1 at runtime-user verification, checksum mismatch |
| Isolated corrupt cache, installation network disabled | Cache rejected; attempted downloader failed explicitly; build exit 1 |

Temporary Dockerfile variants were supplied through stdin. The sentinel was
removed automatically; the existing host grid and production Dockerfile were
not changed by these probes. The downloader's existing checksum/interruption
tests and the new installer's invalid-cache and failed-download tests passed.

No deferred findings remain. Local packaging acceptance is complete; the
separate cadence migration prerequisite remains with the user.

Final checks: `git diff --check` passed; `git diff --exit-code -- .github/workflows`
confirmed unchanged workflows. No images were pushed. Final full-suite
command: `uv run --no-sync pytest -q --tb=short --show-capture=no`.
