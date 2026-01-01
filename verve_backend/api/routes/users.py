import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from verve_backend import crud
from verve_backend.api.common.utils import (
    check_and_raise_primary_key,
    validate_sub_type_id,
)
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, SessionDep, UserSession
from verve_backend.core.security import get_password_hash, verify_password
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    HeatmapSettings,
    User,
    UserCreate,
    UserPassword,
    UserPublic,
    UserSettings,
    UserSettingsPublic,
)
from verve_backend.result import Err, Ok

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=[Tag.USER])


class UserSettingsCollection(BaseModel):
    settings: UserSettingsPublic


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    full_name: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: UserPassword


@router.post("/create", response_model=UserPublic)
def create_user(
    *,
    session: SessionDep,
    user: CurrentUser,
    data: UserCreate,
) -> Any:
    assert user
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Only admin users can create Users"
        )
    match crud.create_user(session=session, user_create=data):
        case Ok(new_user):
            return new_user
        case Err(error_id):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Could not create user. Error code: {error_id}",
            )


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_user_details(
    *,
    user_session: UserSession,
    data: UserUpdate,
) -> Any:
    user_id, session = user_session
    user = session.get(User, user_id)
    assert user is not None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e)) from e
    session.refresh(user)
    return user


@router.patch("/me/password", response_model=UserPublic)
def update_password(
    *,
    user_session: UserSession,
    request: PasswordChangeRequest,
) -> Any:
    user_id, session = user_session
    user = session.get(User, user_id)
    assert user is not None
    if not verify_password(request.old_password, user.hashed_password):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="Old password is incorrect"
        )

    if request.old_password == request.new_password:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="New password must be different"
        )

    user.hashed_password = get_password_hash(request.new_password)
    session.commit()

    return user


@router.put(
    "/me/set_default_activity_type",
)
def set_default_activity_type(
    *,
    user_session: UserSession,
    type_id: int,
    sub_type_id: int | None = None,
) -> JSONResponse:
    user_id, session = user_session
    check_and_raise_primary_key(session, ActivityType, type_id)
    check_and_raise_primary_key(session, ActivitySubType, sub_type_id)

    settings = session.get(UserSettings, user_id)
    assert settings is not None
    settings.default_type_id = type_id
    settings.defautl_sub_type_id = sub_type_id

    session.add(settings)
    session.commit()

    return JSONResponse(content="Defautl activity types updated successfully")


@router.get("/me/settings", response_model=UserSettingsCollection)
def get_user_settings(
    *,
    user_session: UserSession,
) -> Any:
    user_id, session = user_session

    settings = session.get(UserSettings, user_id)
    # A valid user should have a setting
    assert settings is not None

    return UserSettingsCollection(
        settings=UserSettingsPublic.model_validate(settings),
    )


@router.patch("/me/heatmap_settings")
async def replace_heatmap_settings(
    *, user_session: UserSession, data: HeatmapSettings
) -> Any:
    _user_id, session = user_session
    for _type_id, _sub_type_id in data.excluded_activity_types:
        check_and_raise_primary_key(session, ActivityType, _type_id)
        if _sub_type_id is not None:
            check_and_raise_primary_key(session, ActivitySubType, _sub_type_id)
            validate_sub_type_id(session, _type_id, _sub_type_id)

    user_settings = session.get(UserSettings, UUID(_user_id))
    assert user_settings is not None

    user_settings.heatmap_settings = data

    session.add(user_settings)
    session.commit()
