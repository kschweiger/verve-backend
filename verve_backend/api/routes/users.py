import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.status import HTTP_400_BAD_REQUEST

from verve_backend.api.common.db_utils import check_and_raise_primary_key
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, UserSession
from verve_backend.core.security import get_password_hash, verify_password
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    User,
    UserPassword,
    UserPublic,
    UserSettings,
    UserSettingsPublic,
)

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
