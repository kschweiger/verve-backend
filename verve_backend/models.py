import re
import uuid
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Annotated, Generic, TypeVar

from geoalchemy2 import Geography, Geometry
from pydantic import AfterValidator, BaseModel, EmailStr
from sqlalchemy import JSON, Column
from sqlmodel import Field, Index, Relationship, SQLModel, UniqueConstraint

from verve_backend.enums import GoalAggregation, GoalType, TemportalType

T = TypeVar("T", bound=int | float)


def postitive(v: T) -> T:
    assert v > 0, "Value must be > 0"
    return v


PositiveNumber = Annotated[T, AfterValidator(postitive)]
UserPassword = Annotated[str, Field(min_length=8, max_length=40)]


U = TypeVar("U")


class SupportedLocale(StrEnum):
    DE = "de"
    EN = "en"


class EquipmentType(StrEnum):
    BIKE = auto()
    SHOES = auto()
    SKIS = auto()
    SNOWBOARD = auto()
    HOMETRAINER = auto()


class HeatmapSettings(BaseModel):
    """Settings for the heatmap view."""

    excluded_activity_types: list[tuple[int, int | None]] = Field(
        default_factory=list,
        description="List of (type_id, sub_type_id) tuples to exclude from heatmap. "
        "sub_type_id can be None to exclude entire type.",
    )


class ListResponse(BaseModel, Generic[U]):
    data: list[U]


class ActivityEquipment(SQLModel, table=True):
    __tablename__: str = "activity_equipment"  # type: ignore

    activity_id: uuid.UUID = Field(
        foreign_key="activities.id",
        nullable=False,
        ondelete="CASCADE",
        primary_key=True,
    )
    equipment_id: uuid.UUID = Field(
        foreign_key="equipment.id",
        nullable=False,
        ondelete="CASCADE",
        primary_key=True,
    )


# Shared properties
class UserBase(SQLModel):
    name: str = Field(unique=True, min_length=6)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: UserPassword


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


# Database model, database table inferred from class name
class User(UserBase, table=True):
    __tablename__: str = "users"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    is_active: bool = True
    hashed_password: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class ActivityTypeBase(SQLModel):
    name: str = Field(unique=True)


class ActivityTypeCreate(ActivityTypeBase):
    pass


class ActivityTypePublic(ActivityTypeBase):
    id: int


class ActivityType(ActivityTypeBase, table=True):
    __tablename__: str = "activity_type"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)


class ActivitySubTypeBase(SQLModel):
    name: str
    type_id: None | int = Field(default=None, foreign_key="activity_type.id")


class ActivitySubTypeCreate(ActivitySubTypeBase):
    pass


class ActivitySubTypePublic(ActivitySubTypeBase):
    id: int


class ActivitySubType(ActivitySubTypeBase, table=True):
    __tablename__: str = "sub_activity_type"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)

    __table_args__ = (
        UniqueConstraint("name", "type_id", name="uix_subactivity_name_type_id"),
    )


class ActivityBase(SQLModel):
    start: datetime

    duration: timedelta = Field(
        description="Duration of the activity. If string, encoded as ISO8601"
    )
    distance: float = Field(description="Distance traveled in kilometers")
    moving_duration: timedelta | None = Field(
        default=None,
        description="Duration of the activity excluding all points w/o movement."
        " If string, encoded as ISO8601",
    )
    elevation_change_up: float | None = None
    elevation_change_down: float | None = None
    avg_speed: float | None = Field(
        default=None,
        description="Average speed over the duration of the activity in km/h",
    )
    avg_heartrate: float | None = Field(
        default=None,
        description="Average heartrate over the duration of the activity in bpm",
    )
    avg_power: float | None = Field(
        default=None,
        description="Average power over the duration of the activity in watt",
    )
    max_speed: float | None = Field(
        default=None,
        description="Max speed over the duration of the activity in km/h",
    )
    max_heartrate: float | None = Field(
        default=None,
        description="Max heartrate over the duration of the activity in bpm",
    )
    max_power: float | None = Field(
        default=None,
        description="Max power over the duration of the activity in watt",
    )

    type_id: PositiveNumber[int] = Field(foreign_key="activity_type.id", nullable=False)
    sub_type_id: PositiveNumber[int] | None = Field(
        foreign_key="sub_activity_type.id", nullable=True
    )

    name: str = Field(...)
    meta_data: dict = Field(sa_column=Column(JSON), default_factory=dict)


class ActivityCreate(ActivityBase):
    name: str | None


class ActivityPublic(ActivityBase):
    id: uuid.UUID
    created_at: datetime


class Activity(ActivityBase, table=True):
    __tablename__: str = "activities"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=datetime.now)

    equipment: list["Equipment"] = Relationship(
        back_populates="activities",
        link_model=ActivityEquipment,
        sa_relationship_kwargs={
            "lazy": "select",
        },
    )


class EquipmentBase(SQLModel):
    name: str
    equipment_type: EquipmentType
    brand: str | None = None
    model: str | None = None
    description: str | None = None
    purchase_date: datetime | None = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentPublic(EquipmentBase):
    id: uuid.UUID


class Equipment(EquipmentBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE"
    )
    activities: list[Activity] = Relationship(
        back_populates="equipment",
        link_model=ActivityEquipment,
        sa_relationship_kwargs={
            "lazy": "select",
        },
    )


class ActivitiesPublic(SQLModel):
    data: list[ActivityPublic]
    count: int


class TrackPoint(SQLModel, table=True):
    __tablename__ = "track_points"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    activity_id: uuid.UUID = Field(
        foreign_key="activities.id", nullable=False, index=True
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE", index=True
    )
    segment_id: int = Field(...)
    geography: str = Field(sa_column=Column(Geography("POINT", 4326)))
    geometry: str = Field(sa_column=Column(Geometry("POINT")))
    elevation: float | None = Field(default=None)
    time: datetime | None = Field(default=None)

    heartrate: Annotated[int | None, "is_extension"] = Field(default=None)
    cadence: Annotated[int | None, "is_extension"] = Field(default=None)
    power: Annotated[int | None, "is_extension"] = Field(default=None)

    extensions: dict = Field(sa_column=Column(JSON), default_factory=dict)

    __table_args__ = (
        UniqueConstraint("id", "activity_id", name="uix_track_points_id_activity_id"),
        # Multi-column index for common query patterns
        Index("idx_track_points_user_activity", "user_id", "activity_id"),
        Index("idx_track_points_activity_segment", "activity_id", "segment_id"),
    )


class TrackPointResponse(BaseModel):
    segment_id: int
    latitude: float
    longitude: float
    time: datetime
    elevation: float | None

    diff_time: float | None
    diff_distance: float | None
    cum_distance: float

    heartrate: int | None
    cadence: int | None
    power: int | None

    add_extensions: dict[str, int | float] | None = None


class RawTrackData(SQLModel, table=True):
    __tablename__: str = "raw_track_data"  # type: ignore

    activity_id: uuid.UUID = Field(foreign_key="activities.id", primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE", index=True
    )
    store_path: str = Field(...)


class Image(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE", index=True
    )

    activity_id: uuid.UUID | None = Field(foreign_key="activities.id", index=True)


class GoalBase(SQLModel):
    name: str
    description: str | None = None

    current: float = 0
    target: PositiveNumber[float] = Field()
    upper_bound: bool = Field(default=True)
    active: bool = Field(default=True)

    temporal_type: TemportalType = Field(default=TemportalType.YEARLY)
    year: int = Field(default=datetime.now().year)
    month: int | None = Field(default=None)

    type: GoalType = Field()
    aggregation: GoalAggregation = Field()

    constraints: dict = Field(sa_column=Column(JSON), default_factory=dict)


class GoalCreate(GoalBase):
    pass


class GoalPublic(GoalBase):
    id: uuid.UUID
    reached: bool
    progress: float


class Goal(GoalBase, table=True):
    __tablename__: str = "goals"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=datetime.now)


class GoalsPublic(SQLModel):
    data: list[GoalPublic]
    count: int


class LocationBase(SQLModel):
    name: str
    description: str | None = None

    loc: str = Field(sa_column=Column(Geography("POINT", 4326)))


class LocationCreate(LocationBase):
    pass


class LocationPublic(LocationBase):
    id: uuid.UUID
    created_at: datetime


class Location(LocationBase, table=True):
    __tablename__: str = "locations"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=datetime.now)


def is_hex_color_code(value: str) -> str:
    if not re.match(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$", value):
        raise ValueError("Invalid hex color format. Must be #RRGGBB or #RGB")
    return value


class ZoneIntervalBase(SQLModel):
    metric: str
    name: str
    start: float | None
    end: float | None
    color: Annotated[str, AfterValidator(is_hex_color_code)]


class ZoneIntervalCreate(ZoneIntervalBase):
    pass


class ZoneIntervalPublic(ZoneIntervalBase):
    id: uuid.UUID


class ZoneInterval(ZoneIntervalBase, table=True):
    __tablename__: str = "zone_intervals"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime = Field(default_factory=datetime.now)


class UserSettingsBase(SQLModel):
    default_type_id: PositiveNumber[int] = Field(
        foreign_key="activity_type.id", nullable=False
    )
    defautl_sub_type_id: PositiveNumber[int] | None = Field(
        foreign_key="sub_activity_type.id", nullable=True
    )
    locale: SupportedLocale = Field(default=SupportedLocale.EN)
    heatmap_settings: HeatmapSettings = Field(
        sa_column=Column(JSON),
        default_factory=lambda: HeatmapSettings().model_dump(mode="json"),
    )


class UserSettingsPublic(UserSettingsBase):
    pass


class UserSettings(UserSettingsBase, table=True):
    __tablename__: str = "user_settings"  # type: ignore

    user_id: uuid.UUID = Field(
        foreign_key="users.id", primary_key=True, ondelete="CASCADE"
    )


class HighlightMetric(StrEnum):
    DURATION = auto()
    DISTANCE = auto()
    ELEVATION_CHANGE_UP = auto()
    AVG_SPEED = auto()
    MAX_SPEED = auto()


class HighlightTimeScope(StrEnum):
    YEARLY = auto()
    LIFETIME = auto()


class ActivityHighlight(SQLModel, table=True):
    __tablename__: str = "activity_highlights"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    activity_id: uuid.UUID = Field(foreign_key="activities.id", nullable=False)
    type_id: PositiveNumber[int] = Field(foreign_key="activity_type.id", nullable=False)

    metric: HighlightMetric
    scope: HighlightTimeScope
    year: int | None = Field(default=None)
    value: float
    rank: int

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "metric",
            "scope",
            "year",
            "rank",
            "type_id",
            name="uix_highlight_rank",
        ),
    )
