import importlib.resources
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import select, text
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)

from verve_backend import crud
from verve_backend.api.common.track import add_track as upload_track
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import (
    Activity,
    ListResponse,
    SegmentCut,
    SegmentSet,
    TrackPoint,
    TrackPointResponse,
)
from verve_backend.result import Err, Ok
from verve_backend.tasks import process_activity_highlights

logger = structlog.getLogger(__name__)

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

    file_name = file.filename
    assert file_name is not None
    file_content = file.file.read()
    file_content_type = file.content_type

    track, n_points = upload_track(
        activity_id=activity_id,
        user_id=user_id,
        session=session,
        obj_store_client=obj_store_client,
        file_name=file_name,
        file_content=file_content,
        file_content_type=file_content_type,
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

    process_activity_highlights.delay(activity_id=activity_id, user_id=user_id)  # type: ignore

    return JSONResponse(
        status_code=HTTP_201_CREATED,
        content={
            "message": "Track uploaded successfully",
            "activity_id": str(activity_id),
            "number of points": n_points,
        },
    )


class SegementSetCreate(BaseModel):
    name: str
    activity_id: uuid.UUID
    cuts: list[int]


class SegmentSetPublic(BaseModel):
    id: uuid.UUID
    name: str
    activity_id: uuid.UUID


@router.post(
    "/segments/set",
    tags=[Tag.SEGMENTS],
    response_model=SegmentSetPublic,
)
def add_segment_set(user_session: UserSession, segment_set: SegementSetCreate) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    if not session.get(Activity, segment_set.activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")

    if not len(segment_set.cuts):
        raise HTTPException(
            status_code=400, detail="Segment set must have at least one split"
        )

    if len(set(segment_set.cuts)) != len(segment_set.cuts):
        raise HTTPException(status_code=400, detail="Segment set cuts must be unique")

    _cuts = sorted(segment_set.cuts)
    result = crud.add_segment_set(
        session=session,
        user_id=user_id,
        activity_id=segment_set.activity_id,
        name=segment_set.name,
        point_ids=_cuts,
    )
    match result:
        case Ok(set_id):
            logger.info("Segment set %s created successfully", set_id)
            return SegmentSetPublic(
                id=set_id,
                name=segment_set.name,
                activity_id=segment_set.activity_id,
            )
        case Err((err_id, err_msg)):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"{err_msg}. Eror Code: {err_id}",
            )


@router.get(
    "/segments/sets/{activity_id}",
    response_model=ListResponse[uuid.UUID],
    tags=[Tag.SEGMENTS],
)
def get_user_segment_sets(
    user_session: UserSession,
    activity_id: uuid.UUID,
) -> Any:
    _user_id, session = user_session

    data = session.exec(
        select(SegmentSet.id)
        .where(SegmentSet.user_id == uuid.UUID(_user_id))
        .where(SegmentSet.activity_id == activity_id)
    ).all()

    return ListResponse(data=list(data))


@router.delete(
    "/segments/set/{segment_set_id}",
    status_code=HTTP_204_NO_CONTENT,
    tags=[Tag.SEGMENTS],
)
def delete_segment_set(
    user_session: UserSession,
    segment_set_id: uuid.UUID,
) -> None:
    """Delte segment set"""
    _, session = user_session

    _set = session.get(SegmentSet, segment_set_id)
    if _set is None:
        raise HTTPException(status_code=404, detail="Segment set not found")

    session.delete(_set)
    session.commit()


class UpdateSegmentSet(BaseModel):
    name: str | None = None
    cuts: list[int] | None = None


@router.patch(
    "/segments/set/{segment_set_id}",
    status_code=HTTP_200_OK,
    tags=[Tag.SEGMENTS],
)
def update_segment_set(
    user_session: UserSession,
    segment_set_id: uuid.UUID,
    data: UpdateSegmentSet,
) -> Any:
    """Rename segment set and/or update cuts in a segments"""
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    _set = session.get(SegmentSet, segment_set_id)
    if _set is None:
        raise HTTPException(status_code=404, detail="Segment set not found")

    if data.name is None and data.cuts is None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="At least one of name or cuts must be provided for update",
        )

    if data.name:
        logger.debug("Updating set name to %s", data.name)
        _set.name = data.name
        session.commit()

    if data.cuts:
        err = crud.validate_point_ids(
            session=session,
            activity_id=_set.activity_id,
            point_ids=data.cuts,
        )
        if err is not None:
            err_id, err_msg = err
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"{err_msg}. Eror Code: {err_id}",
            )

        _cuts = session.exec(
            select(SegmentCut)
            .where(SegmentCut.set_id == segment_set_id)
            .where(SegmentCut.user_id == user_id)
        ).all()

        err = crud.insert_cuts(
            session=session,
            user_id=user_id,
            set_id=segment_set_id,
            point_ids=data.cuts,
        )
        if err is not None:
            err_id, err_msg = err
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"{err_msg}. Eror Code: {err_id}",
            )
        logger.debug("Deleting previous cuts")
        for cut in _cuts:
            session.delete(cut)
        session.commit()


class SegmentMtrics(BaseModel):
    avg: float
    min: float
    max: float


class SegmentResponse(BaseModel):
    distance: float = Field(description="Distance of the segment in m")
    duration: float = Field(description="Duration of the segment in seconds")

    elevation_gain: float = Field(description="Elevation gain of the segment in m")
    elevation_loss: float = Field(description="Elevation loss of the segment in m")

    speed: SegmentMtrics | None = Field(
        default=None, description="Speed metrics for the segment in m/s"
    )
    heartrate: SegmentMtrics | None = Field(
        default=None, description="Heartrate metrics for the segment in bpm"
    )
    power: SegmentMtrics | None = Field(
        default=None, description="Power metrics for the segment in W"
    )
    cadence: SegmentMtrics | None = Field(
        default=None, description="Cadence metrics for the segment in rpm"
    )

    avg_pace: float | None = Field(
        default=None, description="Average pace of the segment in sec/km"
    )


class SegmentStatisticsResponse(BaseModel):
    segment_id: uuid.UUID
    name: str
    segments: list[SegmentResponse]


@router.get(
    "/segments/set/{segment_set_id}",
    response_model=SegmentStatisticsResponse,
    tags=[Tag.SEGMENTS],
)
def segment_statistics(
    user_session: UserSession,
    segment_set_id: uuid.UUID,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    _set = session.get(SegmentSet, segment_set_id)
    if _set is None:
        raise HTTPException(status_code=404, detail="Segment set not found")

    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("analyze_segments.sql")
        .read_text()
    )

    data = session.exec(
        text(stmt),  # type: ignore
        params=dict(
            segment_set_id=segment_set_id,
            user_id=user_id,
        ),
    )

    data = data.mappings().all()

    _segments = []
    for row in data:
        _row = dict(row)

        hr = None
        if row["max_heartrate"] is not None:
            hr = SegmentMtrics(
                min=row["min_heartrate"],
                max=row["max_heartrate"],
                avg=row["avg_heartrate"],
            )
        speed = None
        if row["max_speed_m_s"] is not None:
            speed = SegmentMtrics(
                min=row["min_speed_m_s"],
                max=row["max_speed_m_s"],
                avg=row["avg_speed_m_s"],
            )
        power = None
        if row["max_power"] is not None:
            power = SegmentMtrics(
                min=row["min_power"],
                max=row["max_power"],
                avg=row["avg_power"],
            )
        cadence = None
        if row["max_cadence"] is not None:
            cadence = SegmentMtrics(
                min=row["min_cadence"],
                max=row["max_cadence"],
                avg=row["avg_cadence"],
            )

        _segments.append(
            SegmentResponse(
                distance=_row["distance_m"],
                duration=_row["elapsed_s"],
                elevation_gain=_row["elevation_gain_m"],
                elevation_loss=_row["elevation_loss_m"],
                heartrate=hr,
                power=power,
                cadence=cadence,
                speed=speed,
                avg_pace=_row["avg_pace_s_per_km"],
            )
        )

    return SegmentStatisticsResponse(
        segment_id=segment_set_id,
        name=_set.name,
        segments=_segments,
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
            id=row.id,
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
            speed=row.speed_m_s,
            heartrate=row.heartrate,
            cadence=row.cadence,
            power=row.power,
            # add_extensions=row.extensions,
        )
        for i, row in enumerate(res)
    ]

    return ListResponse(data=track_points)
