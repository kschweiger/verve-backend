import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from geoalchemy2.shape import to_shape
from sqlmodel import col, func, select
from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    ListResponse,
    Location,
    LocationCreate,
    LocationPublic,
)
from verve_backend.result import Err, Ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/location", tags=[Tag.LOCATION])


def to_public_location(location: Location) -> LocationPublic:
    point = to_shape(location.loc)
    return LocationPublic.model_validate(
        location,
        update={
            "latitude": point.y,  # type: ignore
            "longitude": point.x,  # type: ignore
        },
    )


@router.put("/", response_model=LocationPublic)
async def create_location(
    user_session: UserSession,
    location: LocationCreate,
) -> Any:
    _user_id, session = user_session
    user_id = uuid.UUID(_user_id)

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
) -> Any:
    _, session = user_session

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
                Location.loc,
                func.ST_MakeEnvelope(
                    latitude_lower_bound or -90,
                    latitude_upper_bound or 90,
                    longitude_lower_bound or -180,
                    longitude_upper_bound or 180,
                ),
            )
        )

    location = session.exec(stmt).all()
    return ListResponse[LocationPublic](
        data=[to_public_location(loc) for loc in location],
    )


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
