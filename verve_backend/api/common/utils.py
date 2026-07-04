import datetime
import math
import uuid
from typing import Type, TypeVar

import structlog
from fastapi import HTTPException
from geo_track_analyzer import Track
from sqlmodel import Session, SQLModel
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    DistanceRequirement,
    LocationSubType,
)

logger = structlog.getLogger(__name__)


T = TypeVar("T", bound=SQLModel)


def check_and_raise_primary_key(
    session: Session, obj: Type[T], id: int | uuid.UUID | None
) -> None:
    if id is not None and session.get(obj, id) is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"{obj.__name__} with id {id} not found",
        )


def validate_sub_type_id(
    session: Session,
    model: Type[ActivitySubType] | Type[LocationSubType],
    type_id: int,
    sub_type_id: int,
) -> None:
    sub_type = session.get(model, sub_type_id)
    if sub_type is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} id {id} not found",
        )
    if type_id != sub_type.type_id:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"sub_type {sub_type_id} does not belong to type {type_id}",
        )


def check_distance_requirement(
    session: Session, type_id: int, distance: float | None
) -> None:
    _type = session.get(ActivityType, type_id)
    assert _type is not None

    if _type.distance_requirement == DistanceRequirement.REQUIRED and distance is None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Distance is required for this activity type",
        )
    if (
        _type.distance_requirement == DistanceRequirement.NOT_APPLICABLE
        and distance is not None
    ):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Distance is not applicable for this activity type",
        )


def update_activity_with_track(activity: Activity, track: Track) -> None:
    logger.debug("Getting actuivity infos from track ")
    overview = track.get_track_overview()
    is_stationary = math.isclose(overview.total_distance, 0)
    first_point_time = track.track.segments[0].points[0].time
    if first_point_time:
        activity.start = first_point_time
    activity.distance = None if is_stationary else overview.total_distance_km
    activity.duration = datetime.timedelta(days=0, seconds=overview.total_time_seconds)
    activity.elevation_change_up = overview.uphill_elevation
    activity.elevation_change_down = overview.downhill_elevation
    if not is_stationary:
        activity.moving_duration = datetime.timedelta(
            days=0, seconds=overview.moving_time_seconds
        )
    else:
        activity.moving_duration = None
        activity.avg_speed = None
        activity.max_speed = None
    if overview.velocity_kmh and not is_stationary:
        activity.avg_speed = overview.velocity_kmh.avg
        activity.max_speed = overview.velocity_kmh.max
    if overview.power:
        activity.avg_power = overview.power.avg
        activity.max_power = overview.power.max
    if overview.heartrate:
        activity.avg_heartrate = overview.heartrate.avg
        activity.max_heartrate = overview.heartrate.max
