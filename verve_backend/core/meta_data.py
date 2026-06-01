from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

from verve_backend.models import ActivitySubType, ActivityType

logger = structlog.getLogger(__name__)


class ActivityMetaData(BaseModel):
    target: str

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.target != self.__class__.__name__:
            raise ValueError(
                f"target must be '{self.__class__.__name__}', got '{self.target}'"
            )
        return self


class SwimStyle(StrEnum):
    FREESTYLE = "freestyle"
    BACKSTROKE = "backstroke"
    BREASTSTROKE = "breaststroke"
    BUTTERFLY = "butterfly"
    KICKBOARD = "kickboard"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SetData(BaseModel):
    index: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    durations: timedelta | None = None
    lap_start_index: int | None = None
    lap_end_index: int | None = None
    lap_count: int | None = None
    distance_meters: int | None = None
    style: SwimStyle | None = None
    stroke_count: int | None = None
    avg_swofl: float | None = None
    rest_after: timedelta | None = None


class LapData(BaseModel):
    index: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    durations: timedelta | None = None
    distance_meters: int | None = None
    style: SwimStyle | None = None
    stroke_count: int | None = None
    swolf: float | None = None
    rest_after: timedelta | None = None


class SwimmingMetaData(ActivityMetaData):
    target: str = "SwimmingMetaData"
    pool_length_meters: int | None = None
    total_stroke_count: int | None = None
    avg_swofl: float | None = None
    lap_count: int | None = None
    set_count: int | None = None
    styles: list[SwimStyle] | None = None
    laps: list[LapData] | None = Field(default=None)
    sets: list[SetData] | None = Field(
        default=None,
    )

    @model_validator(mode="after")
    def validate_meta_data(self) -> Self:
        # Check laps/sets and corresponding count variables
        if self.laps and not self.lap_count:
            raise ValueError("lap_count must be provided if laps are included")
        if self.lap_count and not self.laps:
            raise ValueError("laps must be provided if lap_count is included")
        if self.sets and not self.set_count:
            raise ValueError("set_count must be provided if sets are included")
        if self.set_count and not self.sets:
            raise ValueError("sets must be provided if set_count is included")

        required_fields = [
            "pool_length_meters",
            "total_stroke_count",
            "avg_swofl",
            "lap_count",
            "set_count",
            "styles",
            "sets",
            "laps",
        ]
        if not any(getattr(self, f) for f in required_fields):
            raise ValueError(
                "At least one of the following fields must be provided: "
                + ", ".join(required_fields)
            )

        return self


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
