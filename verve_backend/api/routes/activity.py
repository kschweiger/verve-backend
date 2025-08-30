import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import func, select
from starlette.status import HTTP_200_OK, HTTP_415_UNSUPPORTED_MEDIA_TYPE

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import ObjectStoreClient, UserSession
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ActivityPublic,
    Image,
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
def get_activities(user_session: UserSession, limit: int = 100) -> Any:
    _, session = user_session
    count_stmt = select(func.count()).select_from(Activity)
    count = session.exec(count_stmt).one()
    stmt = select(Activity).limit(limit)

    activities = session.exec(stmt).all()

    return ActivitiesPublic(
        data=[ActivityPublic.model_validate(a) for a in activities], count=count
    )


@router.post("/", response_model=ActivityPublic)
def create_activity(*, user_session: UserSession, data: ActivityCreate) -> Any:
    user_id, session = user_session
    activity = Activity.model_validate(data, update={"user_id": user_id})
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
