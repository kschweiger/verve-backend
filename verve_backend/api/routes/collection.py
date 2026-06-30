import datetime
import importlib.resources
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import text
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    UserSession,
)
from verve_backend.models import (
    Activity,
    ActivityCollection,
    ActivityCollectionCreate,
    ActivityCollectionPublic,
)

router = APIRouter(prefix="/collection", tags=[Tag.ACTIVITY, Tag.COLLECTION])

logger = structlog.getLogger(__name__)


def to_public_collection(collection: ActivityCollection) -> ActivityCollectionPublic:
    return ActivityCollectionPublic.model_validate(
        collection, update={"activity_ids": [a.id for a in collection.activities]}
    )


@router.post(
    "",
    response_model=ActivityCollectionPublic,
    tags=[Tag.COLLECTION],
)
def create_collection(
    *, user_session: UserSession, data: ActivityCollectionCreate
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    _activities = []
    for _id in data.activity_ids:
        activity = session.get(Activity, _id)
        if not activity:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND, detail="Activity not found"
            )
        _activities.append(activity)

    _collection = ActivityCollection.model_validate(data, update={"user_id": user_id})
    _collection.activities.extend(_activities)
    session.add(_collection)
    session.commit()
    session.refresh(_collection)

    return to_public_collection(_collection)


class CollectionOverview(BaseModel):
    id: uuid.UUID
    activity_ids: list[uuid.UUID] = Field(
        min_length=1, description="List of activity IDs in the collection"
    )
    name: str
    description: str | None = None
    count: int = Field(ge=1, description="Number of activities in the collection")
    distance: float = Field(
        ge=0, description="Total distance of all activities in the collection"
    )
    moving_duration: datetime.timedelta | None = Field(
        description="Total moving duration of all activities in the collection"
    )
    duration: datetime.timedelta = Field(
        description="Total duration of all activities in the collection"
    )
    start: datetime.datetime = Field(
        description="Start time of the earliest activity in the collection"
    )
    end: datetime.datetime = Field(
        description="End time of the latest activity in the collection"
    )
    elevation_change_up: float | None = None
    elevation_change_down: float | None = None


class CollectionListResponse(BaseModel):
    data: list[CollectionOverview]


@router.get(
    "",
    tags=[Tag.COLLECTION],
    response_model=CollectionListResponse,
)
def get_collections(
    *,
    user_session: UserSession,
    limit: int = 100,
    offset: int | None = None,
    year: Annotated[int | None, Query(ge=2000)] = None,
    month: Annotated[int | None, Query(ge=1, lt=13)] = None,
) -> Any:
    _, session = user_session

    if year is None and month is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Year must be set when month is set",
        )
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("select_collections.sql")
        .read_text()
    )

    rows = session.exec(
        text(stmt),  # type: ignore
        params={
            "year": year,
            "month": month,
            "limit": limit,
            "offset": offset or 0,
        },
    ).all()
    data = [CollectionOverview.model_validate(row._mapping) for row in rows]

    return CollectionListResponse(data=data)


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    activity_ids: list[uuid.UUID] | None = None
    replace_activities: bool = False


@router.patch(
    "/{collection_id}",
    response_model=ActivityCollectionPublic,
    tags=[Tag.COLLECTION],
)
def update_collection(
    *, user_session: UserSession, collection_id: uuid.UUID, data: CollectionUpdate
) -> Any:
    _, session = user_session

    collection = session.get(ActivityCollection, collection_id)
    if collection is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="No data provided for update"
        )
    _activities = []
    if "activity_ids" in update_data:
        if not update_data["activity_ids"]:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="activity_ids cannot be empty if provided",
            )
        for _id in update_data["activity_ids"]:
            _activity = session.get(Activity, _id)
            if _activity is None:
                raise HTTPException(
                    status_code=HTTP_404_NOT_FOUND, detail="Activity not found"
                )
            _activities.append(_activity)

    _replace_activities = update_data.pop("replace_activities", False)

    if "name" in update_data:
        collection.name = update_data["name"]
    if "description" in update_data:
        collection.description = update_data["description"]
    if _activities:
        if _replace_activities:
            collection.activities.clear()
        collection.activities.extend(_activities)

    session.add(collection)
    session.commit()
    session.refresh(collection)

    return to_public_collection(collection)


@router.delete(
    "/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
def delete_collection(
    *,
    user_session: UserSession,
    id: uuid.UUID,
) -> None:
    _, session = user_session

    collection = session.get(ActivityCollection, id)
    if collection is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    session.delete(collection)
    session.commit()
