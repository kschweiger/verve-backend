import importlib.resources
import logging
import uuid
from collections import defaultdict

from geoalchemy2.shape import to_shape
from sqlmodel import Session, text

from verve_backend.core.timing import log_timing
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


@log_timing
def get_activities_for_location(
    session: Session,
    location: Location,
    match_distance: int = 50,
) -> list[uuid.UUID]:
    point = to_shape(location.loc)
    latitude = point.y  # type: ignore
    longitude = point.x  # type: ignore

    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("match_location_to_tracks.sql")
        .read_text()
    )

    data = session.exec(
        text(stmt),  # type: ignore
        params={
            "longitude": longitude,
            "latitude": latitude,
            "match_distance_meters": match_distance,
        },
    ).all()

    return [_id for _id, _ in data]


@log_timing
def get_location_activity_map(
    session: Session,
    match_distance: int = 50,
) -> dict[uuid.UUID, set[uuid.UUID]]:
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("join_locations_to_tracks.sql")
        .read_text()
    )
    data = session.exec(
        text(stmt),  # type: ignore
        params={
            "match_distance_meters": match_distance,
        },
    ).all()

    _map = defaultdict(set)
    for location_id, activity_id, _, _ in data:
        _map[location_id].add(activity_id)

    return _map


@log_timing
def get_activity_locations(
    session: Session,
    activity_id: uuid.UUID,
    match_distance: int = 50,
) -> set[uuid.UUID]:
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("locations_by_activity_id.sql")
        .read_text()
    )
    data = session.exec(
        text(stmt),  # type: ignore
        params={"match_distance_meters": match_distance, "activity_id": activity_id},
    ).all()

    return {_id for _id, _, _ in data}
