import math
from functools import cache

import structlog
from timezonefinder import TimezoneFinder

logger = structlog.getLogger(__name__)


@cache
def _finder() -> TimezoneFinder:
    return TimezoneFinder()


def infer_iana_timezone_from_coordinates(
    *,
    latitude: float,
    longitude: float,
) -> str | None:
    """Return a land timezone, or None for invalid/unresolved coordinates."""
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    try:
        return _finder().timezone_at_land(lat=latitude, lng=longitude)
    except Exception:
        # Keep package failures inside this boundary; uploads use their fallback.
        logger.exception("Coordinate timezone lookup failed")
        return None
