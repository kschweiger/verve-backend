import logging
from datetime import timedelta
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError, model_validator

from verve_backend.models import ActivitySubType, ActivityType

logger = logging.getLogger("uvicorn.error")


class ActivityMetaData(BaseModel):
    target: str

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.target != self.__class__.__name__:
            raise ValueError(
                f"target must be '{self.__class__.__name__}', got '{self.target}'"
            )
        return self


class LapData(BaseModel):
    count: int
    lap_lenths: int | None = None
    style: str | None = None
    duration: timedelta | None = None


class SwimmingMetaData(ActivityMetaData):
    target: str = "SwimmingMetaData"
    segments: list[LapData]


def validate_meta_data(
    activity_type: ActivityType,
    sub_activity_type: ActivitySubType | None,
    data: dict[str, Any],
) -> UUID | ActivityMetaData:
    err_uuid = uuid4()
    md = None
    if activity_type.name == "Swimming":
        try:
            md = SwimmingMetaData.model_validate(data)
        except ValueError as e:
            logger.error("[%s] Erro on meta data validation", err_uuid)
            logger.exception("[%s] %s", err_uuid, e)
            return err_uuid

    assert md is not None, "Meta data validation not implemented for this activity type"
    return md


def parse_meta_data(data: dict[str, Any]) -> ActivityMetaData | None:
    """
    Parses and validates meta data using the 'target' field.
    Automatically discovers the correct model class by name.
    Returns the validated Pydantic model instance or None if validation fails.
    """
    target = data.get("target")
    if not target:
        logger.error("Missing 'target' field in meta data")
        return None

    # Get the model class from the current module's globals
    model_class = globals().get(target)

    if not model_class or not (
        isinstance(model_class, type) and issubclass(model_class, ActivityMetaData)
    ):
        logger.error("Unknown or invalid target type: %s", target)
        return None

    try:
        return model_class.model_validate(data)
    except ValidationError as e:
        logger.error("Error parsing meta data")
        logger.exception("%s", e)
        return None
