from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from verve_backend.schema.meta_data import KnownMetaDataEnvelope

Coordinates = tuple[float, float, float]  # NOTE: Lon, Lat, Ele


def check_length(data: list | None, exp_length: int) -> bool:
    return data is not None and len(data) != exp_length


class VerveBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class MetricSummary(VerveBaseModel):
    """Extensible structure for metric aggregates"""

    avg: float | None = None
    max: float | None = None
    min: float | None = None


class ActivityStats(VerveBaseModel):
    """Grouped statistics"""

    speed: MetricSummary | None = Field(default=None)
    heart_rate: MetricSummary | None = None
    power: MetricSummary | None = Field(default=None)
    cadence: MetricSummary | None = Field(default=None)


class EquipmentExport(VerveBaseModel):
    """Snapshot of equipment used"""

    name: str
    type: str
    brand: str | None = None
    model: str | None = None


class LineStringGeometry(VerveBaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Coordinates]


class LineProperties(VerveBaseModel):
    coord_times: list[datetime] = Field(default_factory=list)
    heart_rates: list[int | None] | None = None
    cadences: list[int | None] | None = None
    powers: list[float | None] | None = None
    temperatures: list[float | None] | None = None


class LineFeature(VerveBaseModel):
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


class VerveProperties(VerveBaseModel):
    # -- Identification --
    verve_version: Literal["1.0"] = "1.0"
    generator: str = "VerveBackend"

    # -- Core Data --
    name: str
    description: str | None = None

    activity_type: str  # e.g. "Cycling"
    activity_sub_type: str | None = None
    start_time: datetime

    # -- Dimensions --
    duration: float = Field(
        description="Total duration in seconds",
        serialization_alias="durationSeconds",
        validation_alias="durationSeconds",
    )

    moving_duration: float | None = Field(
        default=None,
        description="Moving duration in seconds",
        serialization_alias="movingDurationSeconds",
        validation_alias="movingDurationSeconds",
    )

    distance: float | None = Field(
        default=None,
        description="Total distance in m",
        serialization_alias="totalDistanceMeters",
        validation_alias="totalDistanceMeters",
    )

    energy: float | None = Field(
        default=None,
        description="Calories burnt in kcal",
        serialization_alias="totalEnergyKcal",
        validation_alias="totalEnergyKcal",
    )

    elevation_gain: float | None = None
    elevation_loss: float | None = None

    # -- Extensible Aggregates --
    stats: ActivityStats = Field(default_factory=ActivityStats)

    # -- Context --
    equipment: list[EquipmentExport] | None = Field(default=None)
    metadata: KnownMetaDataEnvelope | dict[str, Any] = Field(
        default_factory=dict,
        union_mode="left_to_right",
    )  # The arbitrary JSON blob from DB


class VerveFeature(VerveBaseModel):
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
