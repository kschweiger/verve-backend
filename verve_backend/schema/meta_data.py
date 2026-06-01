from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

from verve_backend.core.meta_data import (
    LapData,
    SetData,
    SwimmingMetaData,
    SwimStyle,
)


class VerveMetaDataModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class SwimLapDataV1(VerveMetaDataModel):
    index: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float | None = None
    distance_meters: int | None = None
    stroke_style: SwimStyle | None = None
    stroke_count: int | None = None
    swolf: float | None = None
    rest_after_seconds: float | None = None


class SwimSetDataV1(VerveMetaDataModel):
    index: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float | None = None
    lap_start_index: int | None = None
    lap_end_index: int | None = None
    lap_count: int | None = None
    distance_meters: int | None = None
    stroke_style: SwimStyle | None = None
    stroke_count: int | None = None
    average_swolf: float | None = None
    rest_after_seconds: float | None = None


class SwimmingMetaDataV1(VerveMetaDataModel):
    pool_length_meters: int | None = None
    total_stroke_count: int | None = None
    average_swolf: float | None = None
    lap_count: int | None = None
    set_count: int | None = None
    stroke_styles: list[SwimStyle] | None = None
    laps: list[SwimLapDataV1] | None = None
    sets: list[SwimSetDataV1] | None = None

    @model_validator(mode="after")
    def validate_meaningful_data(self) -> Self:
        if not any(
            (
                self.pool_length_meters,
                self.total_stroke_count,
                self.average_swolf,
                self.lap_count,
                self.set_count,
                self.stroke_styles,
                self.laps,
                self.sets,
            )
        ):
            raise ValueError("Swimming metadata must contain meaningful swim data")
        return self


class SwimmingMetaDataEnvelopeV1(VerveMetaDataModel):
    target: Literal["SwimmingMetaData"] = "SwimmingMetaData"
    version: Literal["1.0"] = "1.0"
    data: SwimmingMetaDataV1

    def to_core_meta_data(self) -> SwimmingMetaData:
        return SwimmingMetaData(
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
                    distance_meters=None
                    if lap.distance_meters is None
                    else int(lap.distance_meters),
                    style=lap.stroke_style,
                    stroke_count=lap.stroke_count,
                    swolf=lap.swolf,
                    rest_after=_seconds_to_timedelta(lap.rest_after_seconds),
                )
                for lap in self.data.laps or []
            ]
            or None,
            sets=[
                SetData(
                    index=set_data.index,
                    start_time=set_data.start_time,
                    end_time=set_data.end_time,
                    durations=_seconds_to_timedelta(set_data.duration_seconds),
                    lap_start_index=set_data.lap_start_index,
                    lap_end_index=set_data.lap_end_index,
                    lap_count=set_data.lap_count,
                    distance_meters=None
                    if set_data.distance_meters is None
                    else int(set_data.distance_meters),
                    style=set_data.stroke_style,
                    stroke_count=set_data.stroke_count,
                    avg_swofl=set_data.average_swolf,
                    rest_after=_seconds_to_timedelta(set_data.rest_after_seconds),
                )
                for set_data in self.data.sets or []
            ]
            or None,
        )


def _seconds_to_timedelta(seconds: float | None) -> timedelta | None:
    if seconds is None:
        return None
    return timedelta(seconds=seconds)


KnownMetaDataEnvelope = SwimmingMetaDataEnvelopeV1
