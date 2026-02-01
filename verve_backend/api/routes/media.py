import uuid
from io import BytesIO
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select
from starlette.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend.api.common.store_utils import remove_object_from_store
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    ObjectStoreClient,
    UserSession,
)
from verve_backend.core.config import settings
from verve_backend.models import (
    Activity,
    Image,
    ListResponse,
)
from verve_backend.result import is_ok


class ImageURLResponse(BaseModel):
    id: uuid.UUID
    url: str


router = APIRouter(prefix="/media", tags=[Tag.MEDIA])

logger = structlog.getLogger(__name__)


@router.put("/image/activity/{activity_id}", tags=[Tag.IMAGE, Tag.UPLOAD])
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

    file_name_lower = file_name.lower()
    if file_name_lower.endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif file_name_lower.endswith(".png"):
        content_type = "image/png"
    else:
        raise HTTPException(
            status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only .jpg, .jpeg and .png files are supported.",
        )

    file_content = await file.read()

    if len(file_content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=HTTP_413_CONTENT_TOO_LARGE,
            detail="File too large",
        )

    db_obj = Image(
        user_id=user_id,  # type: ignore
        activity_id=activity_id,
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    obj_path = f"images/{db_obj.id}"

    try:
        obj_store_client.upload_fileobj(
            BytesIO(file_content),
            Bucket=settings.BOTO3_BUCKET,
            Key=obj_path,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {
                    "original_filename": file.filename,
                    "uploaded_by": str(user_id),
                    "activity_id": str(activity_id),
                    "file_type": content_type,
                },
            },
        )
    except Exception as e:
        exec_id = uuid.uuid4()
        logger.error("[%s]: %s", exec_id, str(e))
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image. Error Code: %s" % exec_id,
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


@router.get(
    "/image/{image_id}",
    response_model=ImageURLResponse,
    tags=[Tag.IMAGE],
)
async def get_image(
    *,
    user_session: UserSession,
    image_id: uuid.UUID,
    obj_store_client: ObjectStoreClient,
) -> Any:
    _, session = user_session

    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    obj_path = f"images/{image_id}"
    presigned_url = obj_store_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.BOTO3_BUCKET, "Key": obj_path},
        ExpiresIn=3600,  # URL valid for 1 hour
    )

    return ImageURLResponse(id=image.id, url=presigned_url)


@router.delete(
    "/image/{image_id}",
    status_code=HTTP_204_NO_CONTENT,
    tags=[Tag.IMAGE],
)
async def delete_image(
    *,
    user_session: UserSession,
    image_id: uuid.UUID,
    obj_store_client: ObjectStoreClient,
) -> None:
    _, session = user_session

    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    obj_path = f"images/{image_id}"

    result = remove_object_from_store(
        obj_store_client=obj_store_client,
        obj_path=obj_path,
    )
    if is_ok(result):
        session.delete(image)
        session.commit()
    else:
        raise HTTPException(
            status_code=500, detail=f"Failed to check image. Error code {result.error}"
        )


@router.get(
    "/images/activity/{activity_id}",
    tags=[Tag.IMAGE],
    response_model=ListResponse[ImageURLResponse],
)
async def get_activity_images(
    *,
    user_session: UserSession,
    activity_id: uuid.UUID,
    obj_store_client: ObjectStoreClient,
) -> Any:
    _, session = user_session

    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    images = session.exec(select(Image).where(Image.activity_id == activity_id)).all()

    image_data = []
    for img in images:
        obj_path = f"images/{img.id}"
        presigned_url = obj_store_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.BOTO3_BUCKET, "Key": obj_path},
            ExpiresIn=3600,  # URL valid for 1 hour
        )
        image_data.append(
            ImageURLResponse(
                id=img.id,
                url=presigned_url,
            )
        )

    return ListResponse(data=image_data)
