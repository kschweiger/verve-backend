from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from verve_backend.core.date_utils import to_utc_with_default_timezone
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
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    index: int = Field(ge=0, strict=True)
    start_time: datetime | None = None
    end_time: datetime | None = None
    durations: timedelta | None = None
    lap_start_index: int | None = Field(default=None, ge=0, strict=True)
    lap_end_index: int | None = Field(default=None, ge=0, strict=True)
    lap_count: int | None = Field(default=None, ge=0, strict=True)
    distance_meters: float | None = Field(default=None, strict=True)
    style: SwimStyle | None = None
    stroke_count: int | None = Field(default=None, ge=0, strict=True)
    avg_swofl: float | None = Field(default=None, strict=True)
    rest_after: timedelta | None = None

    @field_validator("durations", "rest_after", mode="before")
    @classmethod
    def reject_boolean_duration(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Swimming durations must not be booleans")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time.utcoffset() is not None
            and self.end_time.utcoffset() is not None
            and self.end_time.astimezone(UTC) < self.start_time.astimezone(UTC)
        ):
            raise ValueError("Set end must not precede its start")
        return self


class LapData(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    index: int = Field(ge=0, strict=True)
    start_time: datetime | None = None
    end_time: datetime | None = None
    durations: timedelta | None = None
    distance_meters: float | None = Field(default=None, strict=True)
    style: SwimStyle | None = None
    stroke_count: int | None = Field(default=None, ge=0, strict=True)
    swolf: float | None = Field(default=None, strict=True)
    rest_after: timedelta | None = None

    @field_validator("durations", "rest_after", mode="before")
    @classmethod
    def reject_boolean_duration(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Swimming durations must not be booleans")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time.utcoffset() is not None
            and self.end_time.utcoffset() is not None
            and self.end_time.astimezone(UTC) < self.start_time.astimezone(UTC)
        ):
            raise ValueError("Lap end must not precede its start")
        return self


class SwimmingMetaData(ActivityMetaData):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    target: str = "SwimmingMetaData"
    pool_length_meters: float | None = Field(default=None, strict=True)
    total_stroke_count: int | None = Field(default=None, ge=0, strict=True)
    avg_swofl: float | None = Field(default=None, strict=True)
    lap_count: int | None = Field(default=None, ge=0, strict=True)
    set_count: int | None = Field(default=None, ge=0, strict=True)
    styles: list[SwimStyle] | None = None
    laps: list[LapData] | None = Field(default=None)
    sets: list[SetData] | None = Field(
        default=None,
    )

    @model_validator(mode="after")
    def validate_meta_data(self) -> Self:
        if not any(
            value is not None
            for value in (
                self.pool_length_meters,
                self.total_stroke_count,
                self.avg_swofl,
                self.lap_count,
                self.set_count,
            )
        ) and not any((self.styles, self.laps, self.sets)):
            raise ValueError("Swimming metadata must contain meaningful swim data")
        for records, count in (
            (self.laps, self.lap_count),
            (self.sets, self.set_count),
        ):
            if records is not None and count is not None and len(records) != count:
                raise ValueError("Swimming count must match its array length")
            for index, record in enumerate(records or []):
                if record.index != index:
                    raise ValueError("Swimming index must equal its array position")
        for record in self.sets or []:
            start, end = record.lap_start_index, record.lap_end_index
            for reference in (start, end):
                if reference is not None and (
                    self.laps is None or reference >= len(self.laps)
                ):
                    raise ValueError("Set references must refer to supplied laps")
            if start is not None and end is not None:
                if start > end:
                    raise ValueError("Set lap start must not exceed lap end")
                if record.lap_count is not None and record.lap_count != end - start + 1:
                    raise ValueError("Set lap count must match its inclusive range")
        return self


def normalize_swimming_times_to_utc(
    metadata: SwimmingMetaData, timezone: ZoneInfo
) -> None:
    for records in (metadata.laps, metadata.sets):
        for record in records or []:
            if record.start_time is not None:
                record.start_time = to_utc_with_default_timezone(
                    record.start_time, timezone
                )
            if record.end_time is not None:
                record.end_time = to_utc_with_default_timezone(
                    record.end_time, timezone
                )


def validate_swimming_meta_data(
    data: dict[str, Any], timezone: ZoneInfo
) -> SwimmingMetaData:
    metadata = SwimmingMetaData.model_validate(data)
    normalize_swimming_times_to_utc(metadata, timezone)
    return SwimmingMetaData.model_validate(metadata.model_dump(exclude_unset=True))


def validate_meta_data(
    activity_type: ActivityType,
    sub_activity_type: ActivitySubType | None,
    data: dict[str, Any],
    *,
    timezone: ZoneInfo,
) -> UUID | ActivityMetaData:
    err_uuid = uuid4()
    md = None
    if activity_type.name == "Swimming":
        try:
            md = validate_swimming_meta_data(data, timezone)
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
