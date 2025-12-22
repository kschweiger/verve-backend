import logging

from geoalchemy2.shape import to_shape

from verve_backend.models import (
    Location,
    LocationPublic,
)

logger = logging.getLogger(__name__)


def to_public_location(location: Location) -> LocationPublic:
    point = to_shape(location.loc)
    return LocationPublic.model_validate(
        location,
        update={
            "latitude": point.y,  # type: ignore
            "longitude": point.x,  # type: ignore
        },
    )
