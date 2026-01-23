import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from geo_track_analyzer import GeoJsonTrack
from geo_track_analyzer.exceptions import GeoJsonWithoutGeometryError
from sqlmodel import Session, select

from verve_backend import crud
from verve_backend.exceptions import VerveImportError
from verve_backend.models import (
    Activity,
    Equipment,
)
from verve_backend.result import Err, Ok
from verve_backend.schema.verve_file import (
    VerveFeature,
)

logger = logging.getLogger(__name__)


def sniff_verve_format(data: dict[str, Any]) -> bool:
    """
    Checks if a dictionary looks like a Verve file
    without triggering full Pydantic validation (which is slow).
    """
    try:
        props = data.get("properties", {})
        if not isinstance(props, dict):
            return False

        # 2. Check for Verve Signature
        # This is O(1) lookup, instant.
        if props.get("verveVersion") == "1.0":
            return True

    except Exception:
        return False

    return False


def convert_verve_file_to_activity(
    session: Session,
    user_id: UUID,
    data: VerveFeature,
    overwrite_type_id: None | int = None,
    overwrite_sub_type_id: None | int = None,
) -> Activity:
    logger.debug("Starting verve file conversion")
    match crud.get_type_by_name(session=session, name=data.properties.activity_type):
        case Ok(_type):
            activity_type = _type
            assert activity_type.id is not None
        case Err(_):
            raise VerveImportError(
                f"ActivityType {data.properties.activity_type} not found"
            )
    activity_sub_type = None
    if data.properties.activity_sub_type:
        match crud.get_sub_type_by_name(
            session=session, name=data.properties.activity_sub_type
        ):
            case Ok(_type):
                activity_sub_type = _type
                assert activity_sub_type is not None
            case Err(_):
                raise VerveImportError(
                    f"ActivitySubType {data.properties.activity_sub_type} not found"
                )

        if activity_sub_type.type_id != activity_type.id:
            raise VerveImportError(
                f"ActivitySubType {data.properties.activity_sub_type} does not belong "
                f"to ActivityType {data.properties.activity_type}"
            )
    _type_id = overwrite_type_id if overwrite_type_id is not None else activity_type.id
    if overwrite_sub_type_id is not None:
        _sub_type_id = overwrite_sub_type_id
    else:
        _sub_type_id = activity_sub_type.id if activity_sub_type else None

    logger.error("%s / %s", _type_id, _sub_type_id)
    activity = Activity(
        user_id=user_id,
        created_at=datetime.now(),
        name=data.properties.name,
        type_id=_type_id,
        sub_type_id=_sub_type_id,
        start=data.properties.start_time,
        duration=timedelta(seconds=data.properties.duration),
        distance=None
        if data.properties.distance is None
        else data.properties.distance / 1000,
        moving_duration=timedelta(seconds=data.properties.moving_duration)
        if data.properties.moving_duration
        else None,
        elevation_change_up=data.properties.elevation_gain,
        elevation_change_down=data.properties.elevation_loss,
        energy=data.properties.energy,
        avg_speed=data.properties.stats.speed.avg
        if data.properties.stats.speed
        else None,
        avg_heartrate=data.properties.stats.heart_rate.avg
        if data.properties.stats.heart_rate
        else None,
        avg_power=data.properties.stats.power.avg
        if data.properties.stats.power
        else None,
        max_speed=data.properties.stats.speed.max
        if data.properties.stats.speed
        else None,
        max_heartrate=data.properties.stats.heart_rate.max
        if data.properties.stats.heart_rate
        else None,
        max_power=data.properties.stats.power.max
        if data.properties.stats.power
        else None,
        meta_data=data.properties.metadata,
    )

    if data.properties.equipment:
        for import_equipment in data.properties.equipment:
            db_equipment = session.exec(
                select(Equipment).where(Equipment.name == import_equipment.name)
            )
            if db_equipment is None:
                logger.warning(f"Could not find equipment {import_equipment.name}")
            activity.equipment.extend(db_equipment)

    session.add(activity)
    session.commit()
    session.refresh(activity)

    logger.debug("Converting Verve track to GeoJsonTrack")
    _data = data.model_dump(by_alias=True)

    empty_spatial_flag = False
    try:
        track = GeoJsonTrack(source=_data, max_speed_percentile=99)
    except GeoJsonWithoutGeometryError:
        track = GeoJsonTrack(
            source=_data, allow_empty_spatial=True, max_speed_percentile=99
        )
        empty_spatial_flag = True
    except Exception as e:
        logger.error("Error parsing GeoJsonTrack: %s", e)
        logger.debug("Removing Activity ID: %s", activity.id)
        session.delete(activity)
        session.commit()
        raise VerveImportError("Error parsing track data") from e
    logger.debug("Inserting track data into DB")
    crud.insert_track(
        session=session,
        track=track,
        activity_id=activity.id,
        user_id=user_id,
        no_geometry=empty_spatial_flag,
    )

    if (
        data.properties.stats.speed is None
        or data.properties.stats.power is None
        or data.properties.stats.heart_rate is None
        or data.properties.elevation_gain is None
        or data.properties.moving_duration is None
    ):
        overview = track.get_track_overview()
        if data.properties.stats.speed is None and overview.velocity_kmh:
            activity.avg_speed = overview.velocity_kmh.avg
            activity.max_speed = overview.velocity_kmh.max
        if data.properties.stats.power is None and overview.power:
            activity.avg_power = overview.power.avg
            activity.max_power = overview.power.max
        if data.properties.stats.heart_rate is None and overview.heartrate:
            activity.avg_heartrate = overview.heartrate.avg
            activity.max_heartrate = overview.heartrate.max
        if data.properties.elevation_gain is None:
            activity.elevation_change_up = overview.uphill_elevation
            activity.elevation_change_down = overview.downhill_elevation
        if data.properties.moving_duration is None:
            activity.moving_duration = timedelta(
                days=0, seconds=overview.moving_time_seconds
            )

    session.commit()

    return activity
