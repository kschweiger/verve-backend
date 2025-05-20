import uuid
from datetime import datetime, timedelta
from typing import Annotated, TypeVar

from pydantic import AfterValidator, EmailStr
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, UniqueConstraint

T = TypeVar("T", bound=int | float)


def postitive(v: T) -> T:
    assert v > 0, "Value must be > 0"
    return v


PositiveNumber = Annotated[T, AfterValidator(postitive)]


# Shared properties
class UserBase(SQLModel):
    name: str = Field(unique=True, min_length=6)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


# Database model, database table inferred from class name
class User(UserBase, table=True):
    __tablename__: str = "users"  # type: ignore

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
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
    duration: timedelta

    type_id: PositiveNumber[int] = Field(foreign_key="activity_type.id", nullable=False)
    sub_type_id: PositiveNumber[int] = Field(
        foreign_key="sub_activity_type.id", nullable=False
    )

    meta_data: dict = Field(sa_column=Column(JSON), default_factory=dict)


class ActivityCreate(ActivityBase):
    pass


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


class ActivitiesPublic(SQLModel):
    data: list[ActivityPublic]
    count: int
