import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.highlights.utils import get_public_highlight
from verve_backend.models import (
    Activity,
    ActivityHighlight,
    ActivityHighlightPublic,
    HighlightTimeScope,
    ListResponse,
)

# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/highlights",
    tags=[
        Tag.ACTIVITY,
    ],
)


@router.get("/activity/{id}", response_model=ListResponse[ActivityHighlightPublic])
async def get_highlights_for_activity(
    user_session: UserSession,
    id: uuid.UUID,
    year: int | None = None,
) -> Any:
    """
    Get all highlight metrics for a given activity.
    """
    _, session = user_session

    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    stmt = select(ActivityHighlight).where(ActivityHighlight.activity_id == id)
    if year is not None:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.YEARLY)
        stmt = stmt.where(ActivityHighlight.year == year)
    else:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.LIFETIME)

    highlights = session.exec(stmt).all()

    return ListResponse(data=[get_public_highlight(ah) for ah in highlights])
