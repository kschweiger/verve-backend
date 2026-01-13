import datetime
import logging
import uuid
from io import BytesIO
from time import perf_counter

from fastapi import HTTPException
from geo_track_analyzer import ByteTrack, FITTrack, Track
from geo_track_analyzer.exceptions import (
    EmptyGeoJsonError,
    GeoJsonWithoutGeometryError,
    UnsupportedGeoJsonTypeError,
)
from geo_track_analyzer.track import GeoJsonTrack
from sqlmodel import Session
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.deps import ObjectStoreClient
from verve_backend.core.config import settings
from verve_backend.models import Activity, RawTrackData

logger = logging.getLogger(__name__)


def add_track(
    activity_id: uuid.UUID,
    user_id: uuid.UUID,
    session: Session,
    obj_store_client: ObjectStoreClient,
    file_name: str,
    file_content: bytes,
    file_content_type: str | None,
) -> tuple[Track, int]:
    empty_spatial_flag = False

    if file_name.endswith(".fit"):
        track = FITTrack(BytesIO(file_content), max_speed_percentile=99)  # type: ignore
        orig_file_type = "fit"
    elif file_name.endswith(".gpx"):
        track = ByteTrack(BytesIO(file_content), max_speed_percentile=99)  # type: ignore
        orig_file_type = "gpx"
    elif file_name.endswith(".json"):
        file_bytes = BytesIO(file_content).read()
        try:
            track = GeoJsonTrack(file_bytes, max_speed_percentile=99)  # type: ignore
        except UnsupportedGeoJsonTypeError:
            logger.error("geojson file type not supported")
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GeoJSON file type not supported. Only LineString and "
                "MultiLineString are supported.",
            )
        except EmptyGeoJsonError:
            logger.debug("geojson file empty")
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail="GeoJSON file contains no track data.",
            )
        except GeoJsonWithoutGeometryError:
            logger.debug("geojson file failed without geometry")
            track = GeoJsonTrack(
                file_bytes,
                max_speed_percentile=99,
                allow_empty_spatial=True,
                # TODO: Set default lat/long?
            )  # type: ignore
            empty_spatial_flag = True
        except Exception as e:
            err_uuid = uuid.uuid4()
            logger.error("[%s] geojson file parsing failed", err_uuid)
            logger.error("[%s] %s", err_uuid, e)
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing the GeoJSON file. "
                f"Error Code: {err_uuid}",
            )

        orig_file_type = "json"
    else:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File type not supported. Only .fit, .gpx, and .json files are supported.",
        )
    # TODO: Deal with the empty_spatial_flag pass it ouside?

    activity = session.get(Activity, activity_id)
    if activity is None:
        # This happens if a activity_id for a different user is passed
        # Raise 400 for security
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Activity id not found",
        )

    obj_path = f"tracks/{uuid.uuid4()}"

    obj_store_client.upload_fileobj(
        BytesIO(file_content),
        Bucket=settings.BOTO3_BUCKET,
        Key=obj_path,
        ExtraArgs={
            "ContentType": file_content_type,  # Preserve the MIME type
            "Metadata": {
                "original_filename": file_name,
                "uploaded_by": str(user_id),
                "activity_id": str(activity_id),
                "file_type": orig_file_type,
            },
        },
    )

    raw_data = RawTrackData(
        activity_id=activity_id,
        user_id=user_id,  # type: ignore
        store_path=obj_path,
    )
    session.add(raw_data)
    session.commit()

    pre = perf_counter()
    n_points = crud.insert_track(
        session=session, track=track, activity_id=activity_id, user_id=user_id
    )
    logger.info("Inserting took: %.2f seconds", perf_counter() - pre)

    return track, n_points


def update_activity_with_track(activity: Activity, track: Track) -> None:
    logger.debug("Getting actuivity infos from track ")
    overview = track.get_track_overview()
    first_point_time = track.track.segments[0].points[0].time
    assert first_point_time is not None
    activity.start = first_point_time
    activity.distance = overview.total_distance_km
    activity.duration = datetime.timedelta(days=0, seconds=overview.total_time_seconds)
    activity.elevation_change_up = overview.uphill_elevation
    activity.elevation_change_down = overview.downhill_elevation
    activity.moving_duration = datetime.timedelta(
        days=0, seconds=overview.moving_time_seconds
    )
    if overview.velocity_kmh:
        activity.avg_speed = overview.velocity_kmh.avg
        activity.max_speed = overview.velocity_kmh.max
    if overview.power:
        activity.avg_power = overview.power.avg
        activity.max_power = overview.power.max
    if overview.heartrate:
        activity.avg_heartrate = overview.heartrate.avg
        activity.max_heartrate = overview.heartrate.max
