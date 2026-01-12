from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.aliases import AliasChoices

Coordinates = tuple[float, float, float]  # NOTE: Lon, Lat, Ele


def check_length(data: list | None, exp_length: int) -> bool:
    return data is not None and len(data) != exp_length


class MetricSummary(BaseModel):
    """Extensible structure for metric aggregates"""

    avg: float | None = None
    max: float | None = None
    min: float | None = None


class ActivityStats(BaseModel):
    """Grouped statistics"""

    speed: MetricSummary | None = Field(default=None)

    heart_rate: MetricSummary | None = Field(
        default=None,
        serialization_alias="heartRate",
        validation_alias=AliasChoices("heartRate", "heart_rate"),
    )

    power: MetricSummary | None = Field(default=None)
    cadence: MetricSummary | None = Field(default=None)


class EquipmentExport(BaseModel):
    """Snapshot of equipment used"""

    name: str
    type: str
    brand: str | None = None
    model: str | None = None


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Coordinates]


class LineProperties(BaseModel):
    coord_times: list[datetime] = Field(
        default_factory=list,
        serialization_alias="coordTimes",
        validation_alias=AliasChoices("coordTimes", "coord_times"),
    )

    heart_rates: list[int | None] | None = Field(
        default=None,
        serialization_alias="heartRates",
        validation_alias=AliasChoices("heartRates", "heart_rates"),
    )

    cadences: list[int | None] | None = None
    powers: list[float | None] | None = None
    temperatures: list[float | None] | None = None


class LineFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry | None = None
    properties: LineProperties

    @model_validator(mode="after")
    def validate_array_length(self) -> Self:
        n_time = len(self.properties.coord_times)

        if self.geometry is not None and len(self.geometry.coordinates) != n_time:
            raise ValueError(
                "Length of coordinates does not match length of coord_times"
            )
        if check_length(self.properties.heart_rates, n_time):
            raise ValueError(
                "Length of heart_rates does not match length of coord_times"
            )
        if check_length(self.properties.cadences, n_time):
            raise ValueError("Length of cadences does not match length of coord_times")
        if check_length(self.properties.powers, n_time):
            raise ValueError("Length of powers does not match length of coord_times")
        if check_length(self.properties.temperatures, n_time):
            raise ValueError(
                "Length of temperatures does not match length of coord_times"
            )
        return self


class VerveProperties(BaseModel):
    # -- Identification --
    verve_version: Literal["1.0"] = Field(
        default="1.0",
        serialization_alias="verveVersion",
        validation_alias=AliasChoices("verveVersion", "verve_version"),
    )
    generator: str = "VerveBackend"

    # -- Core Data --
    name: str
    description: str | None = None

    activity_type: str = Field(
        serialization_alias="activityType",
        validation_alias=AliasChoices("activityType", "activity_type"),
    )  # e.g. "Cycling"

    activity_sub_type: str | None = Field(
        default=None,
        serialization_alias="activitySubType",
        validation_alias=AliasChoices("activitySubType", "activity_sub_type"),
    )

    start_time: datetime = Field(
        serialization_alias="startTime",
        validation_alias=AliasChoices("startTime", "start_time"),
    )

    # -- Dimensions --
    duration: float = Field(
        description="Total duration in seconds",
        serialization_alias="durationSeconds",
        validation_alias=AliasChoices("durationSeconds", "duration"),
    )

    moving_duration: float | None = Field(
        default=None,
        description="Moving duration in seconds",
        serialization_alias="movingDurationSeconds",
        validation_alias=AliasChoices("movingDurationSeconds", "moving_duration"),
    )

    distance: float | None = Field(
        default=None,
        description="Total distance in m",
        serialization_alias="totalDistanceMeters",
        validation_alias=AliasChoices("totalDistanceMeters", "distance"),
    )

    energy: float | None = Field(
        default=None,
        description="Calories burnt in kcal",
        serialization_alias="totalEnergyKcal",
        validation_alias=AliasChoices("totalEnergyKcal", "energy"),
    )

    elevation_gain: float | None = Field(
        default=None,
        serialization_alias="elevationGain",
        validation_alias=AliasChoices("elevationGain", "elevation_gain"),
    )

    elevation_loss: float | None = Field(
        default=None,
        serialization_alias="elevationLoss",
        validation_alias=AliasChoices("elevationLoss", "elevation_loss"),
    )

    # -- Extensible Aggregates --
    stats: ActivityStats = Field(default_factory=ActivityStats)

    # -- Context --
    equipment: list[EquipmentExport] | None = Field(default=None)
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )  # The arbitrary JSON blob from DB


class VerveFeature(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[LineFeature]
    properties: VerveProperties

    @field_validator("features", mode="after")
    @classmethod
    def check_length(cls, value: list) -> list:
        if len(value) == 0:
            raise ValueError("At least one feature must be provided")
        return value

    def to_json(self) -> str:
        # by_alias=True is required to trigger serialization_alias
        return self.model_dump_json(by_alias=True, exclude_none=True)
