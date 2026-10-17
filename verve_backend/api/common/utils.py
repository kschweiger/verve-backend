import datetime
import math
import uuid
from typing import TYPE_CHECKING, Type, TypeVar
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException
from geo_track_analyzer import Track
from sqlmodel import Session, SQLModel
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from verve_backend.core.date_utils import to_utc_with_default_timezone
from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    DistanceRequirement,
    LocationSubType,
    UserSettings,
)

if TYPE_CHECKING:
    from verve_backend.schema.verve_file import VerveFeature

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


def apply_verve_activity_data(
    activity: Activity, data: VerveFeature, track: Track
) -> None:
    """Calculate missing summaries, then preserve the validated file's values."""
    props = data.properties
    stats = props.stats
    activity.avg_speed = activity.max_speed = None
    activity.avg_heartrate = activity.max_heartrate = None
    activity.avg_power = activity.max_power = None
    activity.moving_duration = None
    activity.elevation_change_up = activity.elevation_change_down = None

    if any(segment.points for segment in track.track.segments) and (
        stats.speed is None
        or stats.heart_rate is None
        or stats.power is None
        or props.moving_duration is None
        or props.elevation_gain is None
        or props.elevation_loss is None
    ):
        update_activity_with_track(activity, track)

    activity.start = to_utc_with_default_timezone(
        props.start_time, ZoneInfo(activity.timezone)
    )
    activity.duration = datetime.timedelta(seconds=props.duration)
    activity.distance = None if props.distance is None else props.distance / 1000
    activity.energy = props.energy
    if props.moving_duration is not None:
        activity.moving_duration = datetime.timedelta(seconds=props.moving_duration)
    if props.elevation_gain is not None:
        activity.elevation_change_up = props.elevation_gain
    if props.elevation_loss is not None:
        activity.elevation_change_down = props.elevation_loss

    if stats.speed is not None:
        activity.avg_speed = None if stats.speed.avg is None else stats.speed.avg * 3.6
        activity.max_speed = None if stats.speed.max is None else stats.speed.max * 3.6
    if stats.heart_rate is not None:
        activity.avg_heartrate = stats.heart_rate.avg
        activity.max_heartrate = stats.heart_rate.max
    if stats.power is not None:
        activity.avg_power = stats.power.avg
        activity.max_power = stats.power.max


def get_user_timezone(session: Session, user_id: uuid.UUID) -> ZoneInfo:
    settings = session.get(UserSettings, user_id)
    assert settings is not None
    return ZoneInfo(settings.timezone)
