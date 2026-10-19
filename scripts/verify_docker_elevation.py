"""Verify a local runtime image's elevation grid and ASGI startup offline."""

import argparse
import subprocess
import sys

PROBE = r"""
import asyncio
import hashlib
import json
import math
import os
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from verve_backend.core.elevation import (
    ElevationConversionError,
    get_elevation_converter,
)

scenario, expected_machine = sys.argv[1:]
grid = Path("/opt/verve/proj/us_nga_egm08_25.tif")
expected_hash = "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a"
assert (os.geteuid(), os.getegid()) == (1000, 1000), "Unexpected runtime user"
assert platform.machine() == expected_machine, "Unexpected image architecture"
assert os.environ.get("VERVE_EGM2008_GRID") == str(grid), "Unexpected grid path"
assert not Path("/app/data/proj").exists(), "Host grid directory entered image"
with grid.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
assert digest == expected_hash, "Packaged grid checksum mismatch"

# Prime the cache before overrides: lifespan must validate the grid again.
converter = get_elevation_converter()
sea_level = converter.to_sea_level(11.5, 48, 100)
assert math.isclose(sea_level, 53.980892181396484, rel_tol=0, abs_tol=1e-7)
assert math.isclose(
    converter.to_ellipsoidal(11.5, 48, sea_level), 100, rel_tol=0, abs_tol=1e-7
)

from verve_backend.main import app


async def startup():
    async with app.router.lifespan_context(app):
        pass


with TemporaryDirectory(prefix="verve-grid-check-") as temporary:
    override = Path(temporary) / "grid.tif"
    if scenario != "default":
        os.environ["VERVE_EGM2008_GRID"] = str(override)
    if scenario == "override":
        override.symlink_to(grid)
    elif scenario == "corrupt":
        override.write_bytes(b"not an EGM2008 grid")
    elif scenario == "unreadable":
        override.write_bytes(b"unreadable grid")
        override.chmod(0)

    try:
        asyncio.run(startup())
    except ElevationConversionError as exc:
        if scenario == "missing":
            assert "missing" in str(exc), str(exc)
        elif scenario == "corrupt":
            assert "checksum" in str(exc), str(exc)
        elif scenario == "unreadable":
            assert isinstance(exc.__cause__, PermissionError), repr(exc)
        else:
            raise
    else:
        assert scenario in ("default", "override"), "Invalid grid allowed startup"
        assert math.isclose(
            get_elevation_converter().to_sea_level(11.5, 48, 100),
            sea_level,
            rel_tol=0,
            abs_tol=1e-7,
        )

print(json.dumps({
    "scenario": scenario,
    "architecture": platform.machine(),
    "uid": os.geteuid(),
    "gid": os.getegid(),
    "grid": str(grid),
    "sha256": digest,
    "sea_level_m": sea_level,
    "status": "passed",
}), flush=True)
"""

# Explicit, non-production settings allow app imports without local .env files.
PROBE_ENVIRONMENT = {
    "ENVIRONMENT": "testing",
    "SECRET_KEY": "offline-image-verification-only",
    "POSTGRES_SERVER": "127.0.0.1",
    "POSTGRES_USER": "offline",
    "POSTGRES_PASSWORD": "offline",
    "POSTGRES_RLS_PASSWORD": "offline",
    "BOTO3_ENDPOINT": "http://127.0.0.1:9000",
    "BOTO3_ACCESS": "offline",
    "BOTO3_SECRET": "offline",
    "FRONTEND_HOST": "http://localhost:3000",
    "PROJ_NETWORK": "OFF",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="already-built local image reference or ID")
    parser.add_argument(
        "--platform", required=True, choices=("linux/amd64", "linux/arm64")
    )
    args = parser.parse_args(argv)
    machine = {"linux/amd64": "x86_64", "linux/arm64": "aarch64"}[args.platform]
    command = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--network",
        "none",
        "--platform",
        args.platform,
        "--entrypoint",
        "python",
    ]
    for name, value in PROBE_ENVIRONMENT.items():
        command.extend(("--env", f"{name}={value}"))
    print(f"Verifying {args.image} ({args.platform}) offline", flush=True)
    for scenario in ("default", "override", "missing", "corrupt", "unreadable"):
        print(f"Checking {scenario}", flush=True)
        try:
            subprocess.run(
                [*command, args.image, "-", scenario, machine],
                input=PROBE,
                text=True,
                check=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"Verification failed ({scenario}): {exc}", file=sys.stderr)
            return 1
    print("All five offline image checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
