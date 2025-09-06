import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from verve_backend.api.common.db_utils import check_and_raise_primary_key
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, UserSession
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    UserPublic,
    UserSettings,
)

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/users", tags=[Tag.USER])


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.put(
    "/set_default_activity_type",
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
