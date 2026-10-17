"""Reversible WGS 84 ellipsoidal / EGM2008 physical-height conversion."""

import hashlib
import math
import os
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer
from pyproj.enums import TransformDirection
from pyproj.exceptions import ProjError

GRID_NAME = "us_nga_egm08_25.tif"
GRID_SHA256 = "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a"
GRID_URL = f"https://cdn.proj.org/{GRID_NAME}"


class ElevationConversionError(ValueError):
    """A required datum conversion could not be performed reliably."""


def grid_path() -> Path:
    return Path(
        os.environ.get(
            "VERVE_EGM2008_GRID",
            str(Path(__file__).resolve().parents[2] / "data/proj" / GRID_NAME),
        )
    )


class ElevationConverter:
    def __init__(self, path: Path | None = None) -> None:
        path = (path or grid_path()).resolve()
        if not path.is_file():
            raise ElevationConversionError(f"Required EGM2008 grid missing: {path}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != GRID_SHA256:
            raise ElevationConversionError(f"EGM2008 grid checksum mismatch: {path}")
        # An explicit required local grid prevents network and identity fallbacks.
        try:
            self.transformer = Transformer.from_pipeline(
                "+proj=pipeline "
                "+step +proj=unitconvert +xy_in=deg +xy_out=rad "
                f"+step +proj=vgridshift +grids={path} +multiplier=1 "
                "+step +proj=unitconvert +xy_in=rad +xy_out=deg"
            )
        except ProjError as exc:
            raise ElevationConversionError(f"Cannot load EGM2008 grid: {path}") from exc

    def _convert(
        self,
        longitude: float,
        latitude: float,
        height: float,
        direction: TransformDirection,
    ) -> float:
        if not all(math.isfinite(v) for v in (longitude, latitude, height)) or not (
            -180 <= longitude <= 180 and -90 <= latitude <= 90
        ):
            raise ElevationConversionError("Invalid elevation conversion coordinates")
        try:
            _, _, converted = self.transformer.transform(
                longitude, latitude, height, direction=direction, errcheck=True
            )
        except ProjError as exc:
            raise ElevationConversionError(
                "EGM2008 elevation conversion failed"
            ) from exc
        if not math.isfinite(converted):
            raise ElevationConversionError(
                "EGM2008 conversion returned a nonfinite height"
            )
        return float(converted)

    def to_ellipsoidal(self, longitude: float, latitude: float, height: float) -> float:
        return self._convert(longitude, latitude, height, TransformDirection.FORWARD)

    def to_sea_level(self, longitude: float, latitude: float, height: float) -> float:
        return self._convert(longitude, latitude, height, TransformDirection.INVERSE)


@lru_cache(maxsize=4)
def get_elevation_converter() -> ElevationConverter:
    return ElevationConverter()
