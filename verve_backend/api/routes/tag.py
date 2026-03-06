from typing import Any

import structlog
from fastapi import APIRouter
from starlette.status import (
    HTTP_204_NO_CONTENT,
)

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    UserSession,
)
from verve_backend.models import (
    ActivityTagCategoryCreate,
    ActivityTagCategoryPublic,
    ActivityTagCreate,
    ActivityTagPublic,
    ListResponse,
)

router = APIRouter(prefix="/tag", tags=[Tag.TAGGING])

logger = structlog.getLogger(__name__)


@router.put(
    "/category/add",
    status_code=HTTP_204_NO_CONTENT,
)
def add_tag_category(
    *,
    user_session: UserSession,
    obj: ActivityTagCategoryCreate,
) -> None:
    # TODO: Implement
    pass


@router.put(
    "/add",
    status_code=HTTP_204_NO_CONTENT,
)
def add_tag(
    *,
    user_session: UserSession,
    obj: ActivityTagCreate,
) -> None:
    # TODO: Implement
    pass


@router.get("/find", response_model=ListResponse[ActivityTagPublic])
async def find_tag_by_name(*, user_session: UserSession, search_str: str) -> Any:
    """Fuzzy search tag names in the database"""
    # TODO: Implement
    pass


@router.get("/category/find", response_model=ListResponse[ActivityTagCategoryPublic])
async def find_category_by_name(*, user_session: UserSession, search_str: str) -> Any:
    """Fuzzy search tag category names in the database"""
    # TODO: Implement
    pass


@router.get("/{id}", response_model=ActivityTagPublic)
def get_tag(
    *,
    user_session: UserSession,
    id: int,
) -> Any:
    # TODO: Implement
    pass


@router.delete(
    "/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_tag(
    *,
    user_session: UserSession,
    id: int,
) -> None:
    # TODO: Implement
    pass


@router.patch(
    "/category/{category_id}/add/{tag_id}",
    status_code=HTTP_204_NO_CONTENT,
)
def add_tag_to_category(
    *,
    user_session: UserSession,
    category_id: int,
    tag_id: int,
) -> None:
    # TODO: Implement
    pass


@router.get("/category/{id}", response_model=ListResponse[ActivityTagCategoryPublic])
def get_all_tags(*, user_session: UserSession, id: int) -> Any:
    # TODO: Implement
    pass


@router.delete(
    "/category/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_category(*, user_session: UserSession, id: int) -> None:
    # TODO: Implement
    pass
