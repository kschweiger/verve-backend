import datetime
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import func, select
from starlette.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
)

from verve_backend.api.common.db_utils import (
    check_and_raise_primary_key,
    validate_sub_type_id,
)
from verve_backend.api.common.track import add_track
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ActivityPublic,
    ActivitySubType,
    ActivityType,
    Image,
    UserSettings,
)

router = APIRouter(prefix="/activity", tags=[Tag.ACTIVITY])

logger = logging.getLogger("uvicorn.error")


@router.get("/{id}", response_model=ActivityPublic)
def read_activity(user_session: UserSession, id: uuid.UUID) -> Any:
    _, session = user_session
    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.get("/", response_model=ActivitiesPublic)
def get_activities(
    user_session: UserSession,
    limit: int = 100,
    offset: int | None = None,
    year: Annotated[int | None, Query(ge=2000)] = None,
    month: Annotated[int | None, Query(ge=1, lt=13)] = None,
    type_id: int | None = None,
    sub_type_id: int | None = None,
) -> Any:
    _, session = user_session

    if type_id is None and sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if type_id is not None and sub_type_id is not None:
        validate_sub_type_id(session, type_id, sub_type_id)

    if year is None and month is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Year must be set when month is set",
        )

    stmt = select(Activity).limit(limit).order_by(Activity.start.desc())  # type: ignore
    if offset is not None:
        stmt = stmt.offset(offset)
    if year is not None:
        stmt = stmt.where(func.extract("year", Activity.start) == year)  # type: ignore
        if month is not None:
            stmt = stmt.where(func.extract("month", Activity.start) == month)  # type: ignore

    if type_id is not None:
        stmt = stmt.where(Activity.type_id == type_id)
        if sub_type_id is not None:
            stmt = stmt.where(Activity.sub_type_id == sub_type_id)

    activities = session.exec(stmt).all()
    _data = [ActivityPublic.model_validate(a) for a in activities]
    return ActivitiesPublic(
        data=_data,
        count=len(_data),
    )


@router.post("/", response_model=ActivityPublic)
def create_activity(*, user_session: UserSession, data: ActivityCreate) -> Any:
    user_id, session = user_session
    activity = Activity.model_validate(data, update={"user_id": user_id})
    session.add(activity)
    session.commit()
    session.refresh(activity)
    return activity


@router.post("/auto/", response_model=ActivityPublic)
def create_auto_activity(
    *,
    user_session: UserSession,
    obj_store_client: ObjectStoreClient,
    file: UploadFile,
    type_id: int | None = None,
    sub_type_id: int | None = None,
) -> Any:
    user_id, session = user_session

    settings = session.get(UserSettings, user_id)
    assert settings

    check_and_raise_primary_key(session, ActivityType, type_id)
    check_and_raise_primary_key(session, ActivitySubType, sub_type_id)
    if type_id is None and sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if type_id is not None and sub_type_id is not None:
        validate_sub_type_id(session, type_id, sub_type_id)

    _type_id = settings.default_type_id if type_id is None else type_id
    # Use the default sub_type if the type is not passed. otherwise the sub_type is
    # passed as well or None
    _sub_type_id = settings.defautl_sub_type_id if type_id is None else sub_type_id
    activity = Activity(
        user_id=user_id,
        start=datetime.datetime.now(),
        created_at=datetime.datetime.now(),
        duration=datetime.timedelta(seconds=1),
        distance=1,
        type_id=_type_id,
        sub_type_id=_sub_type_id,
    )

    session.add(activity)
    session.commit()
    session.refresh(activity)

    # TODO: Add error handling that removes the activity again
    track, n_points = add_track(
        activity_id=activity.id,
        user_id=user_id,
        session=session,
        obj_store_client=obj_store_client,
        file=file,
    )

    logger.debug("Getting actuivity infos from track ")
    overview = track.get_track_overview()
    first_point_time = track.track.segments[0].points[0].time
    if first_point_time:
        activity.start = first_point_time
    activity.distance = overview.total_distance_km
    activity.duration = datetime.timedelta(days=0, seconds=overview.total_time_seconds)
    activity.elevation_change_up = overview.uphill_elevation
    activity.elevation_change_down = overview.downhill_elevation
    activity.moving_duration = datetime.timedelta(
        days=0, seconds=overview.moving_time_seconds
    )
    activity.avg_speed = overview.avg_velocity_kmh

    session.add(activity)
    session.commit()
    session.refresh(activity)

    return activity


@router.put("/add_image", tags=[Tag.IMAGE, Tag.UPLOAD])
async def add_image(
    *,
    user_session: UserSession,
    activity_id: uuid.UUID,
    obj_store_client: ObjectStoreClient,
    file: UploadFile,
) -> Any:
    user_id, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    file_name = file.filename
    assert file_name is not None, "Could not retrieve file name"

    if file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif file_name.endswith(".png"):
        content_type = "image/png"
    else:
        raise HTTPException(
            status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .jpg, .jpeg and .png files are supported.",
        )

    db_obj = Image(
        user_id=user_id,  # type: ignore
        activity_id=activity_id,
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    obj_path = f"images/{db_obj.id}"

    obj_store_client.upload_fileobj(
        file.file,
        Bucket="verve",
        Key=obj_path,
        ExtraArgs={
            "ContentType": file.content_type,  # Preserve the MIME type
            "Metadata": {
                "original_filename": file.filename,
                "uploaded_by": str(user_id),
                "activity_id": str(activity_id),
                "file_type": content_type,
            },
        },
    )

    logger.info("Uploaded image to %s", obj_path)
    return JSONResponse(
        status_code=HTTP_200_OK,
        content={
            "message": "Image uploaded successfully",
            "activity_id": str(activity_id),
            "id": str(db_obj.id),
        },
    )
