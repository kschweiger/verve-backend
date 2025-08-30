import logging
import uuid
from io import BytesIO
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from geo_track_analyzer import ByteTrack, FITTrack
from pydantic import BaseModel
from sqlmodel import select, text
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from verve_backend import crud
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import Activity, ActivitySubType, ActivityType, RawTrackData

# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/track", tags=[Tag.TRACK])


@router.put("/", tags=[Tag.UPLOAD])
def add_track(
    user_session: UserSession,
    obj_store_client: ObjectStoreClient,
    activity_id: uuid.UUID,
    file: UploadFile,
) -> Any:
    user_id, session = user_session
    file_name = file.filename
    assert file_name is not None, "Could not retrieve file name"
    # Read file content into memory
    file_content = file.file.read()

    if file_name.endswith(".fit"):
        track = FITTrack(BytesIO(file_content))  # type: ignore
        orig_file_type = "fit"
    elif file_name.endswith(".gpx"):
        track = ByteTrack(BytesIO(file_content))  # type: ignore
        orig_file_type = "gpx"
    else:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File type not supported. Only .fit and .gpx files are supported.",
        )

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
        Bucket="verve",
        Key=obj_path,
        ExtraArgs={
            "ContentType": file.content_type,  # Preserve the MIME type
            "Metadata": {
                "original_filename": file.filename,
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

    return JSONResponse(
        status_code=HTTP_201_CREATED,
        content={
            "message": "Track uploaded successfully",
            "activity_id": str(activity_id),
            "number of points": n_points,
        },
    )


class HeatMapResponse(BaseModel):
    points: list[tuple[float, float, float]]


@router.get("/heatmap", response_model=HeatMapResponse)
def get_heatmap(
    user_session: UserSession,
    activity_type_id: int | None = None,
    activity_sub_type_id: int | None = None,
    limit: int | None = None,
) -> Any:
    user_id, session = user_session

    if (
        activity_type_id is not None
        and session.get(ActivityType, activity_type_id) is None
    ):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Activity with id {activity_type_id} not found",
        )
    if activity_type_id is None and activity_sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if (
        activity_sub_type_id is not None
        and session.get(ActivitySubType, activity_sub_type_id) is None
    ):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Sub Activity  with id {activity_sub_type_id} not found",
        )

    sel_ids = None
    if activity_type_id or limit:
        query = select(Activity.id)
        if activity_type_id:
            query = query.where(Activity.type_id == activity_type_id)
        if activity_sub_type_id:
            query = query.where(Activity.sub_type_id == activity_sub_type_id)

        query = query.order_by(Activity.start.desc())
        if limit:
            query = query.limit(limit)
        _sel_ids = session.exec(query).all()
        if not _sel_ids:
            return HeatMapResponse(points=[])
        sel_ids = f"WHERE activity_id in ('{"','".join(map(str, _sel_ids))}')"
    stmt = f"""
    WITH grid_clusters AS (
    SELECT
        FLOOR(ST_X(geometry) / 10) * 10 as grid_x,
        FLOOR(ST_Y(geometry) / 10) * 10 as grid_y,
        COUNT(DISTINCT activity_id) as activity_count,  -- Count unique activities
        COUNT(*) as total_point_count,                  -- Total points (for reference)
        ST_Centroid(ST_Collect(geometry)) as centroid_geom,
        -- Collect original lat/long for any point in the cluster
        array_agg(ST_Y(geography::geometry)) as cluster_latitudes,
        array_agg(ST_X(geography::geometry)) as cluster_longitudes
    FROM verve.track_points
    {sel_ids if sel_ids else ""}
    GROUP BY grid_x, grid_y
    )
    SELECT
        ST_Y(ST_Transform(centroid_geom, 4326)) as latitude,
        ST_X(ST_Transform(centroid_geom, 4326)) as longitude,
        activity_count as point_count
    FROM grid_clusters
    ORDER BY point_count DESC;
        """
    data = session.exec(text(stmt)).all()

    return HeatMapResponse(points=data)
