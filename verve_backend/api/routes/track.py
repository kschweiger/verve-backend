import importlib.resources
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import select, text
from starlette.status import (
    HTTP_201_CREATED,
)

from verve_backend import crud
from verve_backend.api.common.track import add_track as upload_track
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import (
    Activity,
    ListResponse,
    TrackPoint,
    TrackPointResponse,
)
from verve_backend.tasks import process_activity_highlights

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
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)
    track, n_points = upload_track(
        activity_id=activity_id,
        user_id=user_id,
        session=session,
        obj_store_client=obj_store_client,
        file=file,
    )

    try:
        crud.update_activity_with_track_data(
            session=session,
            track=track,
            activity_id=activity_id,
        )
    except Exception as e:
        logger.error(f"Failed to update activity {activity_id} with track data")
        logger.exception(e)
        logger.info("Removing track data")
        # TODO: Implment

    process_activity_highlights.delay(activity_id, user_id)

    return JSONResponse(
        status_code=HTTP_201_CREATED,
        content={
            "message": "Track uploaded successfully",
            "activity_id": str(activity_id),
            "number of points": n_points,
        },
    )


@router.get("/{activity_id}", response_model=ListResponse[TrackPointResponse])
def get_track_data(user_session: UserSession, activity_id: uuid.UUID) -> Any:
    # TODO: Add extensions
    _, session = user_session
    if not session.get(Activity, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")

    check_stmt = (
        select(
            TrackPoint.id,
            TrackPoint.user_id,
            TrackPoint.activity_id,
        )
        .where(TrackPoint.activity_id == activity_id)
        .limit(1)
    )
    if not session.exec(check_stmt).first():
        return ListResponse(data=[])

    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("select_track_data.sql")
        .read_text()
    )
    res = session.exec(
        text(stmt),  # type: ignore
        params={"activity_id": activity_id, "min_distance": 1},
    ).all()
    track_points = [
        TrackPointResponse(
            segment_id=row.segment_id,
            latitude=row.latitude,
            longitude=row.longitude,
            time=row.time,
            elevation=row.elevation,
            diff_time=row.time_diff_seconds,
            diff_distance=row.distance_from_previous,
            cum_distance=0
            if (i == 0 and row.cumulative_distance_m is None)
            else row.cumulative_distance_m,
            heartrate=row.heartrate,
            cadence=row.cadence,
            power=row.power,
            # add_extensions=row.extensions,
        )
        for i, row in enumerate(res)
    ]

    return ListResponse(data=track_points)
