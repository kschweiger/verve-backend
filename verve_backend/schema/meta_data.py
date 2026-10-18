from datetime import UTC, timedelta
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from verve_backend.core.meta_data import (
    LapData,
    SetData,
    SwimmingMetaData,
    SwimStyle,
    normalize_swimming_times_to_utc,
)
from verve_backend.schema.timestamps import FileTimestamp


class VerveMetaDataModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
        allow_inf_nan=False,
    )


class SwimLapDataV1(VerveMetaDataModel):
    index: int = Field(ge=0, strict=True)
    start_time: FileTimestamp | None = None
    end_time: FileTimestamp | None = None
    duration_seconds: float | None = Field(default=None, strict=True)
    distance_meters: float | None = Field(default=None, strict=True)
    stroke_style: SwimStyle | None = None
    stroke_count: int | None = Field(default=None, ge=0, strict=True)
    swolf: float | None = Field(default=None, strict=True)
    rest_after_seconds: float | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time.astimezone(UTC) < self.start_time.astimezone(UTC)
        ):
            raise ValueError("Lap end must not precede its start")
        return self


class SwimSetDataV1(VerveMetaDataModel):
    index: int = Field(ge=0, strict=True)
    start_time: FileTimestamp | None = None
    end_time: FileTimestamp | None = None
    duration_seconds: float | None = Field(default=None, strict=True)
    lap_start_index: int | None = Field(default=None, ge=0, strict=True)
    lap_end_index: int | None = Field(default=None, ge=0, strict=True)
    lap_count: int | None = Field(default=None, ge=0, strict=True)
    distance_meters: float | None = Field(default=None, strict=True)
    stroke_style: SwimStyle | None = None
    stroke_count: int | None = Field(default=None, ge=0, strict=True)
    average_swolf: float | None = Field(default=None, strict=True)
    rest_after_seconds: float | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time.astimezone(UTC) < self.start_time.astimezone(UTC)
        ):
            raise ValueError("Set end must not precede its start")
        return self


class SwimmingMetaDataV1(VerveMetaDataModel):
    pool_length_meters: float | None = Field(default=None, strict=True)
    total_stroke_count: int | None = Field(default=None, ge=0, strict=True)
    average_swolf: float | None = Field(default=None, strict=True)
    lap_count: int | None = Field(default=None, ge=0, strict=True)
    set_count: int | None = Field(default=None, ge=0, strict=True)
    stroke_styles: list[SwimStyle] | None = None
    laps: list[SwimLapDataV1] | None = None
    sets: list[SwimSetDataV1] | None = None

    @model_validator(mode="after")
    def validate_meaningful_data(self) -> Self:
        if not any(
            value is not None
            for value in (
                self.pool_length_meters,
                self.total_stroke_count,
                self.average_swolf,
                self.lap_count,
                self.set_count,
            )
        ) and not any((self.stroke_styles, self.laps, self.sets)):
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


class SwimmingMetaDataEnvelopeV1(VerveMetaDataModel):
    target: Literal["SwimmingMetaData"]
    version: Literal["1.0"]
    data: SwimmingMetaDataV1

    def to_core_meta_data(self, timezone: ZoneInfo) -> SwimmingMetaData:
        metadata = SwimmingMetaData(
            pool_length_meters=self.data.pool_length_meters,
            total_stroke_count=self.data.total_stroke_count,
            avg_swofl=self.data.average_swolf,
            lap_count=self.data.lap_count,
            set_count=self.data.set_count,
            styles=self.data.stroke_styles,
            laps=[
                LapData(
                    index=lap.index,
                    start_time=lap.start_time,
                    end_time=lap.end_time,
                    durations=_seconds_to_timedelta(lap.duration_seconds),
                    distance_meters=lap.distance_meters,
                    style=lap.stroke_style,
                    stroke_count=lap.stroke_count,
                    swolf=lap.swolf,
                    rest_after=_seconds_to_timedelta(lap.rest_after_seconds),
                )
                for lap in self.data.laps or []
            ]
            if self.data.laps is not None
            else None,
            sets=[
                SetData(
                    index=set_data.index,
                    start_time=set_data.start_time,
                    end_time=set_data.end_time,
                    durations=_seconds_to_timedelta(set_data.duration_seconds),
                    lap_start_index=set_data.lap_start_index,
                    lap_end_index=set_data.lap_end_index,
                    lap_count=set_data.lap_count,
                    distance_meters=set_data.distance_meters,
                    style=set_data.stroke_style,
                    stroke_count=set_data.stroke_count,
                    avg_swofl=set_data.average_swolf,
                    rest_after=_seconds_to_timedelta(set_data.rest_after_seconds),
                )
                for set_data in self.data.sets or []
            ]
            if self.data.sets is not None
            else None,
        )
        normalize_swimming_times_to_utc(metadata, timezone)
        return metadata


def _seconds_to_timedelta(seconds: float | None) -> timedelta | None:
    if seconds is None:
        return None
    return timedelta(seconds=seconds)


KnownMetaDataEnvelope = SwimmingMetaDataEnvelopeV1
