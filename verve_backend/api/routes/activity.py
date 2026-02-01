import datetime
import json
import uuid
from io import BytesIO
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, func, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.common.locale import get_activity_name
from verve_backend.api.common.location import to_public_location
from verve_backend.api.common.store_utils import remove_object_from_store
from verve_backend.api.common.track import add_track, update_activity_with_track
from verve_backend.api.common.utils import (
    check_and_raise_primary_key,
    check_distance_requirement,
    validate_sub_type_id,
)
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    LocaleQuery,
    ObjectStoreClient,
    UserSession,
)
from verve_backend.api.routes.media import delete_image
from verve_backend.core.config import settings
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ActivityPublic,
    ActivitySubType,
    ActivityType,
    EquipmentSet,
    Image,
    ListResponse,
    Location,
    LocationPublic,
    RawTrackData,
    TrackPoint,
    User,
    UserSettings,
)
from verve_backend.result import Err, Ok, is_ok
from verve_backend.schema.importer import (
    convert_verve_file_to_activity,
    sniff_verve_format,
)
from verve_backend.schema.verve_file import VerveFeature
from verve_backend.tasks import process_activity_highlights


class ActivityUpdate(BaseModel):
    type_id: int | None = None
    sub_type_id: int | None = None
    meta_data: dict | None = None
    name: str | None = None


router = APIRouter(prefix="/activity", tags=[Tag.ACTIVITY])

logger = structlog.getLogger(__name__)


@router.get("/{id}", response_model=ActivityPublic)
def read_activity(user_session: UserSession, id: uuid.UUID) -> Any:
    _, session = user_session
    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    return activity


@router.patch("/{id}", response_model=ActivityPublic)
def update_activity(
    user_session: UserSession,
    id: uuid.UUID,
    data: ActivityUpdate,
) -> Any:
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    update_data = data.model_dump(exclude_unset=True)

    if "type_id" in update_data:
        if update_data["type_id"] is None:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST, detail="type_id cannot be set to null"
            )
        # Check that both fit together
        if "sub_type_id" in update_data and update_data["sub_type_id"] is not None:
            validate_sub_type_id(
                session,
                ActivitySubType,
                update_data["type_id"],
                update_data["sub_type_id"],
            )
        if "sub_type_id" not in update_data and activity.sub_type_id is not None:
            # Check that the current sub_type fits to the new type
            validate_sub_type_id(
                session, ActivitySubType, update_data["type_id"], activity.sub_type_id
            )

        # Check that the new type_id works with the activity distance
        check_distance_requirement(
            session=session,
            type_id=update_data["type_id"],
            distance=activity.distance,
        )
    # Check that ne new sub_id matches the current type_id
    if (
        "type_id" not in update_data
        and "sub_type_id" in update_data
        and update_data["sub_type_id"] is not None
    ):
        validate_sub_type_id(
            session, ActivitySubType, activity.type_id, update_data["sub_type_id"]
        )
    if "meta_data" in update_data and update_data["meta_data"] is None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="meta_data cannot be set to null"
        )
    for field, value in update_data.items():
        setattr(activity, field, value)

    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e)) from e
    session.refresh(activity)
    return activity


@router.delete(
    "/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
async def delete_activity(
    user_session: UserSession,
    obj_store_client: ObjectStoreClient,
    id: uuid.UUID,
) -> None:
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    track_point_count_stmt = (
        select(func.count())
        .select_from(TrackPoint)
        .where(TrackPoint.activity_id == activity.id)
    )
    track_point_count = session.exec(track_point_count_stmt).one()
    if track_point_count > 0:
        track_point_del_stmt = delete(TrackPoint).where(
            col(TrackPoint.activity_id) == activity.id
        )

        try:
            session.exec(track_point_del_stmt)
        except Exception as e:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not delete activity track points. Error: {e}",
            )

        raw_data = session.get(RawTrackData, activity.id)
        if raw_data:
            result = remove_object_from_store(obj_store_client, raw_data.store_path)
            if is_ok(result):
                session.delete(raw_data)
            else:
                session.rollback()
                raise HTTPException(
                    status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not delete activity raw data. "
                    f"Error code: {result.error}",
                )
    images = session.exec(select(Image).where(Image.activity_id == id)).all()
    for image in images:
        await delete_image(
            user_session=user_session,
            image_id=image.id,
            obj_store_client=obj_store_client,
        )
        try:
            session.delete(image)
        except Exception as e:
            session.rollback()
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not delete activity image {image.id}. Error: {e}",
            )

    try:
        session.delete(activity)
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not delete activity. Error: {e}",
        )
    session.commit()


@router.get(
    "/{id}/locations", response_model=ListResponse[LocationPublic], tags=[Tag.LOCATION]
)
async def get_locations_for_activity(
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    response_data = []

    location_ids = crud.get_activity_locations(session, activity.id)
    for _id in location_ids:
        location = session.get(Location, _id)
        assert location is not None

        response_data.append(to_public_location(location))

    return ListResponse(data=response_data)


@router.patch("/{id}/add_location", tags=[Tag.LOCATION])
async def add_locations_to_activity(
    user_session: UserSession,
    id: uuid.UUID,
    location_id: uuid.UUID,
) -> Any:
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    location = session.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Location not found")

    activity.locations.append(location)
    session.commit()

    return {"detail": "Location added to activity"}


@router.delete(
    "/{id}/locations/{location_id}",
    tags=[Tag.LOCATION],
    status_code=HTTP_204_NO_CONTENT,
)
async def delete_location_from_activity(
    user_session: UserSession,
    id: uuid.UUID,
    location_id: uuid.UUID,
) -> None:
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")

    location = session.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Location not found")

    if location not in activity.locations:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Location not associated with activity",
        )
    activity.locations.remove(location)
    session.commit()

    return


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
        validate_sub_type_id(session, ActivitySubType, type_id, sub_type_id)

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
def create_activity(
    *,
    user_session: UserSession,
    locale: LocaleQuery | None = None,
    data: ActivityCreate,
    add_default_equipment: bool = False,
) -> Any:
    user_id, session = user_session
    user = session.get(User, user_id)
    assert user is not None
    if locale is None:
        settings = session.get(UserSettings, user_id)
        assert settings is not None
        locale = settings.locale

    check_distance_requirement(
        session=session, type_id=data.type_id, distance=data.distance
    )

    result = crud.create_activity(
        session=session,
        create=data,
        user=user,  # type: ignore
        locale=locale,
    )
    match result:
        case Ok(_activity):
            activity = _activity
        case Err(error_id):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Received invilaid meta_data for activity. "
                f"Error code: {error_id}",
            )

    if add_default_equipment:
        match crud.get_default_equipment_set(
            session=session,
            user_id=user.id,
            activity_type_id=data.type_id,
            activity_sub_type_id=data.sub_type_id,
        ):
            case Ok(set_id):
                if set_id:
                    logger.debug("Found default equipment set %s", set_id)
                    equipment_set = session.get(EquipmentSet, set_id)
                    assert equipment_set is not None
                    activity.equipment.extend(equipment_set.items)
                    session.commit()
                    session.refresh(activity)
            case Err(err):
                raise HTTPException(
                    status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not retrieve default equipment. Error code: {err}",
                )

    return activity


def _import_verve_file(
    session: Session,
    obj_store_client: ObjectStoreClient,
    user_id: uuid.UUID,
    file_name: str,
    file_content: bytes,
    file_content_type: str | None,
    overwrite_type_id: None | int,
    overwrite_sub_type_id: None | int,
) -> Activity:
    if not file_name.endswith(".json"):
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File type not supported. Only .json files are supported.",
        )

    try:
        data = VerveFeature.model_validate_json(file_content)
    except ValueError as e:
        err_uuid = uuid.uuid4()
        logger.error("[%s] verve json parsing failed", err_uuid)
        logger.error("[%s] %s", err_uuid, e)
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Could not parse Verve JSON file. Error code {err_uuid}",
        )

    activity = convert_verve_file_to_activity(
        session=session,
        user_id=user_id,
        data=data,
        overwrite_type_id=overwrite_type_id,
        overwrite_sub_type_id=overwrite_sub_type_id,
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
                "activity_id": str(activity.id),
                "file_type": "json",
            },
        },
    )

    raw_data = RawTrackData(
        activity_id=activity.id,
        user_id=user_id,
        store_path=obj_path,
    )
    session.add(raw_data)
    session.commit()

    return activity


@router.post("/auto/", response_model=ActivityPublic)
def create_auto_activity(
    *,
    user_session: UserSession,
    obj_store_client: ObjectStoreClient,
    file: UploadFile,
    type_id: int | None = None,
    sub_type_id: int | None = None,
    locale: LocaleQuery | None = None,
    add_default_equipment: bool = False,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    settings = session.get(UserSettings, user_id)
    assert settings

    file_name = file.filename
    assert file_name is not None
    file_content = file.file.read()
    file_content_type = file.content_type

    check_and_raise_primary_key(session, ActivityType, type_id)
    check_and_raise_primary_key(session, ActivitySubType, sub_type_id)
    if type_id is None and sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if type_id is not None and sub_type_id is not None:
        validate_sub_type_id(session, ActivitySubType, type_id, sub_type_id)

    if file_name.endswith(".json") and sniff_verve_format(
        json.loads(file_content.decode("utf-8"))
    ):
        logger.info("Identified verve file")
        activity = _import_verve_file(
            session=session,
            obj_store_client=obj_store_client,
            user_id=user_id,
            file_name=file_name,
            file_content=file_content,
            file_content_type=file_content_type,
            overwrite_type_id=type_id,
            overwrite_sub_type_id=sub_type_id,
        )
    else:
        logger.info("Identified standalone track data")

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
            name="placeholder",
        )

        session.add(activity)
        session.commit()
        session.refresh(activity)

        if add_default_equipment:
            match crud.get_default_equipment_set(
                session=session,
                user_id=user_id,
                activity_type_id=_type_id,
                activity_sub_type_id=_sub_type_id,
            ):
                case Ok(set_id):
                    if set_id:
                        logger.debug("Found default equipment set %s", set_id)
                        equipment_set = session.get(EquipmentSet, set_id)
                        assert equipment_set is not None
                        activity.equipment.extend(equipment_set.items)
                        session.commit()
                        session.refresh(activity)
                case Err(err):
                    raise HTTPException(
                        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Could not retrieve default equipment. "
                        f"Error code: {err}",
                    )

        activity_type = session.get(ActivityType, activity.type_id)
        assert activity_type is not None
        # TODO: Add error handling that removes the activity again
        track, _ = add_track(
            activity_id=activity.id,
            user_id=user_id,
            session=session,
            obj_store_client=obj_store_client,
            file_name=file_name,
            file_content=file_content,
            file_content_type=file_content_type,
        )

        update_activity_with_track(activity=activity, track=track)

        first_point_time = track.track.segments[0].points[0].time
        assert first_point_time is not None
        activity.name = get_activity_name(
            activity_type.name.lower().replace(" ", "_"),
            first_point_time,
            locale or settings.locale,
        )
        session.add(activity)
        session.commit()
        session.refresh(activity)

        session.commit()

    process_activity_highlights.delay(activity.id, user_id)  # type: ignore

    return activity


@router.post("/import/", response_model=ActivityPublic)
def import_verve_file(
    *,
    user_session: UserSession,
    obj_store_client: ObjectStoreClient,
    file: UploadFile,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    file_name = file.filename
    assert file_name is not None
    file_content = file.file.read()
    file_content_type = file.content_type

    activity = _import_verve_file(
        session=session,
        obj_store_client=obj_store_client,
        user_id=user_id,
        file_name=file_name,
        file_content=file_content,
        file_content_type=file_content_type,
        overwrite_type_id=None,
        overwrite_sub_type_id=None,
    )

    process_activity_highlights.delay(activity.id, user_id)  # type: ignore

    return activity
