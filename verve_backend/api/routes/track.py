import importlib.resources
import uuid
from enum import StrEnum
from typing import Any, Literal, Self

import structlog
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select, text
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.common.track import (
    add_track as upload_track,
)
from verve_backend.api.common.track import (
    get_track_points_response,
)
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import (
    Activity,
    ActivityType,
    ListResponse,
    SegmentCut,
    SegmentSet,
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


class SegmentMetrics(BaseModel):
    avg: float
    min: float | None
    max: float | None


class SegmentMetric(StrEnum):
    PACE = "pace"
    HEARTRATE = "heartrate"
    POWER = "power"
    SPEED = "speed"
    CADENCE = "cadence"


class SegmentResponse(BaseModel):
    distance_m: float | None = Field(description="Distance of the segment in m")
    duration_s: float = Field(description="Duration of the segment in seconds")

    elevation_gain: float | None = Field(
        description="Elevation gain of the segment in m"
    )
    elevation_loss: float | None = Field(
        description="Elevation loss of the segment in m"
    )

    speed: SegmentMetrics | None = Field(
        default=None, description="Speed metrics for the segment in m/s"
    )
    heartrate: SegmentMetrics | None = Field(
        default=None, description="Heartrate metrics for the segment in bpm"
    )
    power: SegmentMetrics | None = Field(
        default=None, description="Power metrics for the segment in W"
    )
    cadence: SegmentMetrics | None = Field(
        default=None, description="Cadence metrics for the segment in rpm"
    )
    pace: SegmentMetrics | None = Field(
        default=None, description="Pace of the segment in sec/km"
    )


class SegmentDisplayMetadata(BaseModel):
    """Defines how the frontend should display the segment"""

    primary_metric: SegmentMetric
    display_metrics: list[SegmentMetric]
    speed_unit: Literal["m/s", "km/h", "miles/h"] = "km/h"
    pace_unit: Literal["s/km", "s/mile", "min/km", "min/mile"] = "min/km"

    @model_validator(mode="after")
    def check_primary_in_display(self) -> Self:
        if self.primary_metric not in self.display_metrics:
            raise ValueError("Primary metric must be included in display metrics")
        return self


class SegmentStatisticsResponse(BaseModel):
    segment_set_id: uuid.UUID
    name: str
    segments: list[SegmentResponse]
    cuts: list[int]
    display_metadata: SegmentDisplayMetadata


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

    activitiy = session.get(Activity, _set.activity_id)
    if activitiy is None:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Activity not found"
        )

    _cuts = session.exec(
        select(SegmentCut.point_id)
        .where(SegmentCut.set_id == segment_set_id)
        .where(SegmentCut.user_id == user_id)
    ).all()

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
    has_speed = False
    has_heartrate = False
    has_power = False
    has_cadence = False
    has_pace = False
    for row in data:
        _row = dict(row)

        hr = None
        if row["max_heartrate"] is not None:
            has_heartrate = True
            hr = SegmentMetrics(
                min=row["min_heartrate"],
                max=row["max_heartrate"],
                avg=row["avg_heartrate"],
            )
        speed = None
        if row["max_speed_m_s"] is not None:
            has_speed = True
            speed = SegmentMetrics(
                min=row["min_speed_m_s"],
                max=row["max_speed_m_s"],
                avg=row["avg_speed_m_s"],
            )
        power = None
        if row["max_power"] is not None:
            has_power = True
            power = SegmentMetrics(
                min=row["min_power"],
                max=row["max_power"],
                avg=row["avg_power"],
            )
        cadence = None
        if row["max_cadence"] is not None:
            has_cadence = True
            cadence = SegmentMetrics(
                min=row["min_cadence"],
                max=row["max_cadence"],
                avg=row["avg_cadence"],
            )

        pace = None
        if row["avg_pace_s_per_km"] is not None:
            has_pace = True
            pace = SegmentMetrics(
                avg=row["avg_pace_s_per_km"],
                max=None,
                min=None,
            )

        _segments.append(
            SegmentResponse(
                distance_m=_row["distance_m"],
                duration_s=_row["elapsed_s"],
                elevation_gain=_row["elevation_gain_m"],
                elevation_loss=_row["elevation_loss_m"],
                heartrate=hr,
                power=power,
                cadence=cadence,
                speed=speed,
                pace=pace,
            )
        )

    _types = session.exec(select(ActivityType)).all()

    types = {t.name: t.id for t in _types}

    primary_metric = SegmentMetric.SPEED
    display_metrics = []

    if activitiy.type_id == types["Cycling"]:
        if has_power:
            primary_metric = SegmentMetric.POWER
        elif has_heartrate:
            primary_metric = SegmentMetric.HEARTRATE

    elif activitiy.type_id == types["Foot Sports"]:  # noqa: SIM102
        if has_pace:
            primary_metric = SegmentMetric.PACE
            display_metrics.append(SegmentMetric.PACE)

    if has_speed:
        display_metrics.append(SegmentMetric.SPEED)
    if has_power:
        display_metrics.append(SegmentMetric.POWER)
    if has_heartrate:
        display_metrics.append(SegmentMetric.HEARTRATE)
    if has_cadence:
        display_metrics.append(SegmentMetric.CADENCE)

    if len(display_metrics) == 0:
        err_code = uuid.uuid4()
        logger.error("[%s] No display metrics in set %s", err_code, _set.id)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Error. Error code: {err_code}",
        )

    if primary_metric not in display_metrics:
        primary_metric = display_metrics[0]

    display_metadata = SegmentDisplayMetadata(
        primary_metric=primary_metric, display_metrics=display_metrics
    )
    return SegmentStatisticsResponse(
        segment_set_id=segment_set_id,
        name=_set.name,
        segments=_segments,
        cuts=list(_cuts),
        display_metadata=display_metadata,
    )


@router.get("/{activity_id}", response_model=ListResponse[TrackPointResponse])
def get_track_data(user_session: UserSession, activity_id: uuid.UUID) -> Any:
    # TODO: Add extensions
    _, session = user_session
    if not session.get(Activity, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")

    return ListResponse(
        data=get_track_points_response(
            session=session,
            activity_id=activity_id,
        )
    )
