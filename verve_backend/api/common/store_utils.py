import uuid

import structlog
from botocore.client import ClientError

from verve_backend.api.deps import ObjectStoreClient
from verve_backend.core.config import settings
from verve_backend.result import Err, Ok, Result

logger = structlog.getLogger(__name__)


def remove_object_from_store(
    obj_store_client: ObjectStoreClient, obj_path: str
) -> Result[None, uuid.UUID]:
    err_uuid = uuid.uuid4()
    try:
        obj_store_client.head_object(Bucket=settings.BOTO3_BUCKET, Key=obj_path)
        object_exists = True
        logger.debug("Object %s exists in storage", obj_path)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":  # type: ignore
            object_exists = False
            logger.warning("Image %s exists in DB but not in storage", obj_path)
        else:
            logger.error(
                "[%s] Error checking existence of image %s", err_uuid, obj_path
            )
            return Err(err_uuid)

    try:
        response = obj_store_client.delete_object(
            Bucket=settings.BOTO3_BUCKET,
            Key=obj_path,
        )

        # Check if versioning is enabled and object had a DeleteMarker
        if "DeleteMarker" in response:
            logger.debug("Delete marker added for image %s", obj_path)

        if object_exists:
            logger.info("Successfully deleted image %s from storage", obj_path)
        else:
            logger.warning("Image %s was already missing from storage", obj_path)

    except ClientError as e:
        logger.error("[%s] Failed to delete image %s from storage", err_uuid, obj_path)
        logger.error(str(e))
        return Err(err_uuid)

    logger.debug("Image %s deletion process completed", obj_path)
    return Ok(None)
