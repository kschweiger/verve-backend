from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Coordinates = tuple[float, float, float]  # NOTE: Lon, Lat, Ele


class MetricSummary(BaseModel):
    """Extensible structure for metric aggregates"""

    avg: float | None = None
    max: float | None = None
    min: float | None = None


class ActivityStats(BaseModel):
    """Grouped statistics"""

    speed: MetricSummary = Field(default_factory=MetricSummary)
    heart_rate: MetricSummary = Field(default_factory=MetricSummary, alias="heartRate")
    power: MetricSummary = Field(default_factory=MetricSummary)
    cadence: MetricSummary = Field(default_factory=MetricSummary)


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
    coord_times: list[datetime] = Field(default_factory=list, alias="coordTimes")
    heart_rates: list[int | None] | None = Field(default=None, alias="heartRates")
    cadences: list[int | None] | None = None
    powers: list[float | None] | None = None
    temperatures: list[float | None] | None = None


class LineFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry | None
    properties: LineProperties


class VerveProperties(BaseModel):
    # -- Identification --
    verve_version: Literal["1.0"] = Field(default="1.0", alias="verveVersion")
    generator: str = "VerveBackend"

    # -- Core Data --
    name: str
    description: str | None = None
    activity_type: str = Field(alias="activityType")  # e.g. "Cycling"
    activity_sub_type: str | None = Field(default=None, alias="activitySubType")

    start_time: datetime = Field(alias="startTime")

    # -- Dimensions --
    duration: float = Field(
        description="Total duration in seconds", alias="durationSeconds"
    )
    moving_duration: float | None = Field(
        default=None,
        description="Moving duration in seconds",
        alias="movingDistanceSeconds",
    )
    distance: float | None = Field(
        default=None, description="Total distance in m", alias="totalDistanceMeters"
    )
    energy: float | None = Field(
        default=None, description="Calories burnt in kcal", alias="totalEnergyKcal"
    )

    elevation_gain: float | None = Field(default=None, alias="elevationGain")
    elevation_loss: float | None = Field(default=None, alias="elevationLoss")

    # -- Extensible Aggregates --
    stats: ActivityStats = Field(default_factory=ActivityStats)

    # -- Context --
    equipment: list[EquipmentExport] = Field(default_factory=list)
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
        return self.model_dump_json(by_alias=True, exclude_none=True)
