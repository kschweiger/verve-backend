import logging
import uuid
from io import BytesIO
from time import perf_counter

from fastapi import HTTPException, UploadFile
from geo_track_analyzer import ByteTrack, FITTrack, Track
from sqlmodel import Session
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from verve_backend import crud
from verve_backend.api.deps import ObjectStoreClient
from verve_backend.models import Activity, RawTrackData

logger = logging.getLogger("uvicorn.error")


def add_track(
    activity_id: uuid.UUID,
    user_id: uuid.UUID,
    session: Session,
    obj_store_client: ObjectStoreClient,
    file: UploadFile,
) -> tuple[Track, int]:
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

    return track, n_points
