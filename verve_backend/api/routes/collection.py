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

from verve_backend.api.common.track import get_track_points_response
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    UserSession,
)
from verve_backend.models import (
    Activity,
    ActivityCollection,
    ActivityCollectionCreate,
    ActivityCollectionPublic,
    ActivityPublic,
    CollectionTrackPointResponse,
    ListResponse,
)

router = APIRouter(prefix="/collection", tags=[Tag.ACTIVITY, Tag.COLLECTION])

logger = structlog.getLogger(__name__)


def to_public_collection(collection: ActivityCollection) -> ActivityCollectionPublic:
    activities = sorted(collection.activities, key=lambda a: (a.start, a.id))
    return ActivityCollectionPublic.model_validate(
        collection,
        update={"activity_ids": [a.id for a in activities]},
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

    if len(set(data.activity_ids)) != len(data.activity_ids):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Duplicate activity IDs are not allowed",
        )

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
    distance: float | None = Field(
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
    "/{id}",
    response_model=ActivityCollectionPublic,
    tags=[Tag.COLLECTION],
)
def update_collection(
    *, user_session: UserSession, id: uuid.UUID, data: CollectionUpdate
) -> Any:
    _, session = user_session

    collection = session.get(ActivityCollection, id)
    if collection is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="No data provided for update"
        )
    _activities: list[Activity] = []
    if "activity_ids" in update_data:
        if not update_data["activity_ids"]:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="activity_ids cannot be empty if provided",
            )

        if len(set(update_data["activity_ids"])) != len(update_data["activity_ids"]):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Duplicate activity IDs are not allowed",
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
        else:
            existing_ids = {a.id for a in collection.activities}
            if any(a.id in existing_ids for a in _activities):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="Some activities are already in the collection",
                )
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


class CollectionDetailResponse(BaseModel):
    id: uuid.UUID

    name: str
    description: str | None = None
    activities: list[ActivityPublic]

    total_distance: float | None
    total_duration: datetime.timedelta
    total_moving_duration: datetime.timedelta | None
    total_elevation_change_up: float | None
    total_elevation_change_down: float | None


def sum_optional_float(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def sum_optional_timedelta(
    values: list[datetime.timedelta | None],
) -> datetime.timedelta | None:
    present = [v for v in values if v is not None]
    return sum(present, datetime.timedelta()) if present else None


@router.get(
    "/{id}",
    response_model=CollectionDetailResponse,
)
def get_collection(
    *,
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session

    collection = session.get(ActivityCollection, id)
    if collection is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Collection not found"
        )

    activities = sorted(collection.activities, key=lambda a: (a.start, a.id))

    return CollectionDetailResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        total_distance=sum_optional_float([a.distance for a in activities]),
        total_duration=sum(
            (a.duration for a in activities),
            datetime.timedelta(),
        ),
        total_moving_duration=sum_optional_timedelta(
            [a.moving_duration for a in activities]
        ),
        total_elevation_change_up=sum_optional_float(
            [a.elevation_change_up for a in activities]
        ),
        total_elevation_change_down=sum_optional_float(
            [a.elevation_change_down for a in activities]
        ),
        activities=[ActivityPublic.model_validate(a) for a in activities],
    )


@router.get(
    "/{id}/track",
    response_model=ListResponse[CollectionTrackPointResponse],
)
def get_collection_track(
    *,
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session

    collection = session.get(ActivityCollection, id)
    if collection is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Collection not found"
        )
    points = []
    collection_cum_distance = 0.0

    for activity_index, activity in enumerate(
        sorted(collection.activities, key=lambda a: (a.start, a.id))
    ):
        activity_points = get_track_points_response(session, activity.id)

        for point in activity_points:
            if point.diff_distance is not None:
                collection_cum_distance += point.diff_distance

            points.append(
                CollectionTrackPointResponse(
                    **point.model_dump(),
                    activity_id=activity.id,
                    activity_index=activity_index,
                    collection_cum_distance=collection_cum_distance,
                )
            )

    return ListResponse[CollectionTrackPointResponse](data=points)
