from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlmodel import Session, select

from verve_backend import crud
from verve_backend.api.common.track import parse_track
from verve_backend.api.common.utils import apply_verve_activity_data
from verve_backend.core.date_utils import to_utc_with_default_timezone
from verve_backend.exceptions import VerveImportError
from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    Equipment,
)
from verve_backend.result import Err, Ok
from verve_backend.schema.meta_data import KnownMetaDataEnvelope
from verve_backend.schema.verve_file import VerveFeature

logger = structlog.getLogger(__name__)


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
    timezone: ZoneInfo,
    overwrite_type_id: int | None = None,
    overwrite_sub_type_id: int | None = None,
    timezone_name: str | None = None,
) -> Activity:
    logger.debug("Starting verve file conversion")
    match crud.get_by_name(
        session=session, name=data.properties.activity_type, model=ActivityType
    ):
        case Ok(_type):
            activity_type = _type
            assert activity_type.id is not None
        case Err(_):
            raise VerveImportError(
                f"ActivityType {data.properties.activity_type} not found"
            )
    activity_sub_type = None
    if data.properties.activity_sub_type:
        match crud.get_by_name(
            session=session,
            name=data.properties.activity_sub_type,
            model=ActivitySubType,
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

    parsed = parse_track(
        file_name="verve.json",
        file_content=data.to_json().encode(),
        fallback_timezone=timezone,
        timezone_name=timezone_name,
        verve_timezone=data.properties.timezone,
    )
    timezone = parsed.timezone
    track = parsed.track
    track.track.segments = [
        segment for segment in track.track.segments if segment.points
    ]
    meta_data = data.properties.metadata
    if isinstance(meta_data, KnownMetaDataEnvelope):
        meta_data = meta_data.to_core_meta_data(timezone).model_dump(mode="json")

    activity = Activity(
        user_id=user_id,
        timezone=timezone.key,
        created_at=datetime.now(UTC),
        name=data.properties.name,
        type_id=_type_id,
        sub_type_id=_sub_type_id,
        start=to_utc_with_default_timezone(data.properties.start_time, timezone),
        duration=timedelta(seconds=data.properties.duration),
        distance=None,
        meta_data=meta_data,
    )
    apply_verve_activity_data(activity, data, track)

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

    logger.debug("Inserting track data into DB")
    crud.insert_track(
        session=session,
        track=track,
        activity_id=activity.id,
        user_id=user_id,
        no_geometry=parsed.no_geometry,
    )

    return activity
