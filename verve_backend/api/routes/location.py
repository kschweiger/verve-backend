import uuid
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import col, func, select
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.common.location import (
    to_public_location,
)
from verve_backend.api.common.utils import validate_sub_type_id
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.core.config import settings
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityPublic,
    ActivitySubType,
    DictResponse,
    ListResponse,
    Location,
    LocationCreate,
    LocationPublic,
    LocationSubType,
)
from verve_backend.result import Err, Ok

logger = structlog.getLogger(__name__)

router = APIRouter(prefix="/location", tags=[Tag.LOCATION])


@router.put("/", response_model=LocationPublic)
async def create_location(
    user_session: UserSession,
    location: LocationCreate,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

    if location.type_id is None:
        sub_type_by_name = crud.get_by_name(
            session=session, model=LocationSubType, name="Landmark"
        ).unwrap()
        location.type_id = sub_type_by_name.type_id
        location.sub_type_id = sub_type_by_name.id

    result = crud.create_location(session=session, user_id=user_id, data=location)
    match result:
        case Ok(created_location):
            return to_public_location(created_location)
        case Err(_id):
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create location. Errorcode %s" % _id,
            )


@router.get("/", response_model=ListResponse[LocationPublic])
async def get_all_locations(
    user_session: UserSession,
    limit: Annotated[int, Query(gt=0, le=100)] = 20,
    offset: Annotated[int | None, Query(ge=0)] = None,
    latitude_lower_bound: Annotated[float | None, Query(ge=-90, le=90)] = None,
    latitude_upper_bound: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude_lower_bound: Annotated[float | None, Query(ge=-180, le=180)] = None,
    longitude_upper_bound: Annotated[float | None, Query(ge=-180, le=180)] = None,
    type_id: int | None = None,
    sub_type_id: int | None = None,
) -> Any:
    _, session = user_session

    if type_id is None and sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if type_id is not None and sub_type_id is not None:
        validate_sub_type_id(session, LocationSubType, type_id, sub_type_id)

    stmt = select(Location).limit(limit).order_by(col(Location.created_at).desc())
    if offset:
        stmt.offset(offset)

    if any(
        b
        for b in [
            latitude_lower_bound,
            latitude_upper_bound,
            longitude_lower_bound,
            longitude_upper_bound,
        ]
    ):
        stmt = stmt.where(
            func.ST_Intersects(
                func.ST_GeomFromWKB(Location.loc),
                func.ST_MakeEnvelope(
                    longitude_lower_bound or -179.999,
                    latitude_lower_bound or -89.999,
                    longitude_upper_bound or 179.999,
                    latitude_upper_bound or 89.999,
                    4326,
                ),
            )
        )

    if type_id is not None:
        stmt = stmt.where(Location.type_id == type_id)
        if sub_type_id is not None:
            stmt = stmt.where(Location.sub_type_id == sub_type_id)

    logger.debug("Executing location query: %s", stmt)
    location = session.exec(stmt).all()
    return ListResponse[LocationPublic](
        data=[to_public_location(loc) for loc in location],
    )


@router.get("/activities", response_model=DictResponse[uuid.UUID, set[uuid.UUID]])
async def get_all_activities(
    user_session: UserSession,
    location_type_id: int | None = None,
    location_sub_type_id: int | None = None,
    activity_type_id: int | None = None,
    activity_sub_type_id: int | None = None,
) -> Any:
    _, session = user_session

    if location_type_id is None and location_sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if location_type_id is not None and location_sub_type_id is not None:
        validate_sub_type_id(
            session, LocationSubType, location_type_id, location_sub_type_id
        )

    if activity_type_id is None and activity_sub_type_id is not None:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Sub Activity must be set together with Activity",
        )
    if activity_type_id is not None and activity_sub_type_id is not None:
        validate_sub_type_id(
            session, ActivitySubType, activity_type_id, activity_sub_type_id
        )

    location_activity_map = crud.get_location_activity_map(
        session,
        settings.LOCATION_MATCH_RADIUS_METERS,
        location_type_id=location_type_id,
        location_sub_type_id=location_sub_type_id,
        activity_type_id=activity_type_id,
        activity_sub_type_id=activity_sub_type_id,
    )

    return DictResponse(data=location_activity_map)


@router.get("/{id}", response_model=LocationPublic)
async def get_location(
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session

    location = session.get(Location, id)
    if not location:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Location {id} not found"
        )

    return to_public_location(location)


@router.delete("/{id}")
async def delete_location(
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session
    location = session.get(Location, id)
    if not location:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Location {id} not found"
        )

    try:
        session.delete(location)
        session.commit()
    except Exception as e:
        err_id = uuid.uuid4()
        logger.error("[%s] %s", err_id, e)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete location. Errorcode %s" % err_id,
        )


@router.post("/{id}", response_model=LocationPublic)
async def update_location(
    user_session: UserSession,
    id: uuid.UUID,
    attribute: Literal["name", "description"],
    value: str,
) -> Any:
    _, session = user_session
    if attribute not in ["name", "description"]:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Attribute {attribute} not updatable",
        )

    location = session.get(Location, id)
    if not location:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Location {id} not found"
        )

    match attribute:
        case "name":
            location.name = value
        case "description":
            location.description = value

    session.add(location)
    session.commit()
    session.refresh(location)

    return to_public_location(location)


@router.get(
    "/{id}/activities", response_model=ActivitiesPublic, tags=[Tag.ACTIVITY, Tag.TRACK]
)
def get_activities_with_location(
    user_session: UserSession,
    id: uuid.UUID,
) -> Any:
    _, session = user_session

    location = session.get(Location, id)
    if not location:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Location {id} not found"
        )

    activities = []
    for _id in crud.get_activities_for_location(
        session, location, settings.LOCATION_MATCH_RADIUS_METERS
    ):
        _activity = session.get(Activity, _id)
        assert _activity is not None
        activities.append(ActivityPublic.model_validate(_activity))

    return ActivitiesPublic(data=activities, count=len(activities))


@router.patch("/{id}/replace_type", response_model=LocationPublic)
def updated_location_type(
    user_session: UserSession,
    id: uuid.UUID,
    type_id: int,
    sub_type_id: int,
) -> Any:
    _, session = user_session

    location = session.get(Location, id)
    if not location:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Location {id} not found"
        )

    validate_sub_type_id(
        session=session, model=LocationSubType, type_id=type_id, sub_type_id=sub_type_id
    )

    location.type_id = type_id
    location.sub_type_id = sub_type_id
    session.add(location)
    session.commit()
    session.refresh(location)

    return to_public_location(location)
