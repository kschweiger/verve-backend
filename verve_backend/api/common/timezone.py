from zoneinfo import ZoneInfo

from pydantic import TypeAdapter
from pydantic_extra_types.timezone_name import TimeZoneName

from verve_backend.core.timezone_lookup import infer_iana_timezone_from_coordinates

_timezone_name = TypeAdapter(TimeZoneName)


def resolve_activity_timezone(
    *,
    fallback_timezone: ZoneInfo,
    timezone_name: str | None = None,
    verve_timezone: str | None = None,
    coordinates: tuple[float, float] | None = None,
) -> ZoneInfo:
    """Choose request, Verve property, first timed GPS point, then fallback."""
    declared = timezone_name if timezone_name is not None else verve_timezone
    if declared is not None:
        return ZoneInfo(_timezone_name.validate_python(declared))
    if coordinates is not None:
        latitude, longitude = coordinates
        inferred = infer_iana_timezone_from_coordinates(
            latitude=latitude,
            longitude=longitude,
        )
        if inferred is not None:
            return ZoneInfo(_timezone_name.validate_python(inferred))
    return fallback_timezone
