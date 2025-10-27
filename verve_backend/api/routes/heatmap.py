import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import func, select, text
from starlette.status import (
    HTTP_400_BAD_REQUEST,
)

from verve_backend.api.common.db_utils import check_and_raise_primary_key
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
)


class HeatMapResponse(BaseModel):
    points: list[tuple[float, float, float]]
    center: tuple[float, float] | None


# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/heatmap",
    tags=[Tag.TRACK, Tag.ACTIVITY, Tag.HEATMAP],
)


@router.get("/activities", response_model=HeatMapResponse)
def get_heatmap(
    user_session: UserSession,
    year: Annotated[int | None, Query(ge=2000)] = None,
    month: Annotated[int | None, Query(ge=1, lt=13)] = None,
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
    if year is None and month is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Year must be set when month is set",
        )

    sel_ids = None
    if activity_type_id or limit or year or month:
        query = select(Activity.id)
        if activity_type_id:
            query = query.where(Activity.type_id == activity_type_id)
        if activity_sub_type_id:
            query = query.where(Activity.sub_type_id == activity_sub_type_id)
        if year is not None:
            query = query.where(func.extract("year", Activity.start) == year)  # type: ignore
            if month is not None:
                query = query.where(func.extract("month", Activity.start) == month)  # type: ignore

        query = query.order_by(Activity.start.desc())
        if limit:
            query = query.limit(limit)
        _sel_ids = session.exec(query).all()
        if not _sel_ids:
            return HeatMapResponse(points=[], center=None)
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

    return HeatMapResponse(
        points=data,
        # NOTE: Use the max point as center
        center=(data[0][0], data[0][1]) if data else None,
    )
