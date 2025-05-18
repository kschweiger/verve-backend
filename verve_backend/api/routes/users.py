from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from verve_backend.api.deps import CurrentUser, SessionDep
from verve_backend.models import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user
