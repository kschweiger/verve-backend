from typing import Any

from fastapi import APIRouter

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser
from verve_backend.models import UserPublic

router = APIRouter(prefix="/users", tags=[Tag.USER])


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user
