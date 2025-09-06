import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select, text
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
)

from verve_backend.api.common.db_utils import check_and_raise_primary_key
from verve_backend.api.common.track import add_track as upload_track
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import Activity, ActivitySubType, ActivityType

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

    _, n_points = upload_track(
        activity_id=activity_id,
        user_id=user_id,
        session=session,
        obj_store_client=obj_store_client,
        file=file,
    )

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

    check_and_raise_primary_key(session, ActivityType, activity_type_id)
    if activity_type_id is None and activity_sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    check_and_raise_primary_key(session, ActivitySubType, activity_sub_type_id)

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
