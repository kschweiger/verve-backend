"""Prepare a verified cached grid for an image, or verify its runtime installation."""

import argparse
import math
import shutil
from pathlib import Path

from verve_backend.cli.download_elevation_grid import main as download_grid
from verve_backend.core.elevation import (
    ElevationConversionError,
    ElevationConverter,
    grid_path,
)


def install(destination: Path) -> None:
    cached = grid_path()
    try:
        ElevationConverter(cached)
    except ElevationConversionError:
        download_grid()
        ElevationConverter(cached)
    else:
        print(f"Reusing checksum-verified EGM2008 grid: {cached}", flush=True)

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    shutil.copyfile(cached, destination)
    destination.chmod(0o644)
    ElevationConverter(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument(
        "--destination", type=Path, help="copy the verified cached grid to this path"
    )
    operation.add_argument(
        "--verify-only", action="store_true", help="verify the configured runtime grid"
    )
    args = parser.parse_args(argv)
    if args.verify_only:
        height = ElevationConverter().to_sea_level(11.5, 48, 100)
        if not math.isclose(height, 53.980892181396484, rel_tol=0, abs_tol=1e-7):
            raise ElevationConversionError("EGM2008 control-point conversion failed")
        print(f"Verified EGM2008 grid: {grid_path()} ({height} m)", flush=True)
    else:
        install(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
