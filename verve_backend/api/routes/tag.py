from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import DatabaseError
from sqlmodel import col, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from verve_backend import crud
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import (
    UserSession,
)
from verve_backend.models import (
    Activity,
    ActivityPublic,
    ActivityTag,
    ActivityTagCategory,
    ActivityTagCategoryCreate,
    ActivityTagCategoryPublic,
    ActivityTagCreate,
    ActivityTagLink,
    ActivityTagPublic,
    ListResponse,
)

router = APIRouter(prefix="/tag", tags=[Tag.TAGGING])

logger = structlog.getLogger(__name__)


@router.put(
    "/category/add",
    response_model=ActivityTagCategoryPublic,
)
def add_tag_category(
    *,
    user_session: UserSession,
    obj: ActivityTagCategoryCreate,
) -> Any:
    _user_id, session = user_session
    user_id = UUID(_user_id)

    cat = ActivityTagCategory.model_validate(obj, update={"user_id": user_id})
    try:
        session.add(cat)
        session.commit()
    except DatabaseError as e:
        logger.error("Failed to add tag category", error=str(e))
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Tag category with this name already exists",
        )

    return cat


@router.put(
    "/add",
    response_model=ActivityTagPublic,
)
def add_tag(
    *,
    user_session: UserSession,
    obj: ActivityTagCreate,
) -> Any:
    _user_id, session = user_session
    user_id = UUID(_user_id)

    passed_cat_id = obj.category_id

    if passed_cat_id is not None:
        _cat = session.get(ActivityTagCategory, passed_cat_id)
        if _cat is None:
            logger.error("Got invalid category id for tag creation")
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Invalid category id",
            )
    tag = ActivityTag.model_validate(obj, update={"user_id": user_id})
    try:
        session.add(tag)
        session.commit()
    except DatabaseError as e:
        logger.error("Failed to add tag ", error=str(e))
        session.rollback()
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Tag category with this name already exists",
        )

    return tag


@router.get("/search", response_model=ListResponse[tuple[int, str, float]])
async def find_tag_by_name(
    *,
    user_session: UserSession,
    query: str,
    limit: int = 20,
    similarity_threshold: float = 0.3,
) -> Any:
    """Fuzzy search tag names in the database"""
    _, session = user_session

    data = crud.search_by_name(
        session=session,
        table_name="activity_tags",
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
    )
    return ListResponse(data=data)


@router.get("/category/find", response_model=ListResponse[tuple[int, str, float]])
async def find_category_by_name(
    *,
    user_session: UserSession,
    query: str,
    limit: int = 20,
    similarity_threshold: float = 0.3,
) -> Any:
    """Fuzzy search tag category names in the database"""
    _, session = user_session
    data = crud.search_by_name(
        session=session,
        table_name="activity_tag_categories",
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
    )
    return ListResponse(data=data)


@router.get("/{id}", response_model=ActivityTagPublic)
def get_tag(
    *,
    user_session: UserSession,
    id: int,
) -> Any:
    _, session = user_session
    tag = session.get(ActivityTag, id)
    if not tag:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Tag {id} not found"
        )

    return tag


@router.delete(
    "/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_tag(
    *,
    user_session: UserSession,
    id: int,
) -> None:
    _, session = user_session
    tag = session.get(ActivityTag, id)
    if not tag:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Tag not found")

    session.delete(tag)
    session.commit()


@router.get("/{id}/activities", response_model=ListResponse[ActivityPublic])
async def get_activities_for_tag(
    *,
    user_session: UserSession,
    id: int,
) -> Any:
    _, session = user_session
    tag = session.get(ActivityTag, id)
    if not tag:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Tag not found")

    stmt = (
        select(Activity)
        .join(
            ActivityTagLink,
            col(Activity.id) == col(ActivityTagLink.activity_id),
        )
        .where(
            col(ActivityTagLink.tag_id) == id,
        )
    )

    activities = session.exec(stmt).all()

    return ListResponse(data=list(map(ActivityPublic.model_validate, activities)))


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
    _, session = user_session
    category = session.get(ActivityTagCategory, category_id)
    if not category:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Category not found")

    tag = session.get(ActivityTag, tag_id)
    if not tag:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Tag not found")

    tag.category_id = category_id
    session.add(tag)
    session.commit()


@router.get("/category/{id}", response_model=ListResponse[ActivityTagCategoryPublic])
def get_all_tags(*, user_session: UserSession, id: int) -> Any:
    _, session = user_session
    category = session.get(ActivityTagCategory, id)
    if not category:
        return ListResponse(data=[])

    tags = session.exec(select(ActivityTag).where(ActivityTag.category_id == id)).all()
    return ListResponse(data=list(tags))


@router.delete(
    "/category/{id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_category(
    *, user_session: UserSession, id: int, cascade: bool = False
) -> None:
    """
    Deleta a category. If cascade is True, all tags connected to the category will also
    be deleted. If cascalade is False, the category_id of all tags connected to the
    category will be set to None.
    """
    _, session = user_session
    category = session.get(ActivityTagCategory, id)
    if not category:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Category not found")

    tags = session.exec(select(ActivityTag).where(ActivityTag.category_id == id)).all()
    if cascade:
        for tag in tags:
            session.delete(tag)
            session.commit()
    else:
        for tag in tags:
            tag.category_id = None
            session.add(tag)
            session.commit()

    session.delete(category)
    session.commit()
