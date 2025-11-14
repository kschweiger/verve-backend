import logging
import uuid
from collections import defaultdict
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
    DictResponse,
    HighlightMetric,
    HighlightTimeScope,
    ListResponse,
)

# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/highlights",
    tags=[Tag.ACTIVITY, Tag.HIGHLIGHTS],
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


@router.get(
    "/", response_model=DictResponse[HighlightMetric, list[ActivityHighlightPublic]]
)
def get_highlights(
    user_session: UserSession,
    year: int | None = None,
) -> Any:
    _, session = user_session

    stmt = select(ActivityHighlight)
    if year is not None:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.YEARLY)
        stmt = stmt.where(ActivityHighlight.year == year)
    else:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.LIFETIME)

    highlights = session.exec(stmt).all()
    if not highlights:
        return DictResponse(data={})

    results = defaultdict(list)
    for hl in highlights:
        _hl = get_public_highlight(hl)
        results[hl.metric].append(_hl)

    for metric in results:
        results[metric].sort(key=lambda h: h.rank)
    return DictResponse(data=results)


@router.get("/metric/{metric}", response_model=ListResponse[ActivityHighlightPublic])
def get_highlights_by_metric(
    user_session: UserSession,
    metric: HighlightMetric,
    year: int | None = None,
) -> Any:
    _, session = user_session

    stmt = select(ActivityHighlight).where(ActivityHighlight.metric == metric)
    if year is not None:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.YEARLY)
        stmt = stmt.where(ActivityHighlight.year == year)
    else:
        stmt = stmt.where(ActivityHighlight.scope == HighlightTimeScope.LIFETIME)

    highlights = session.exec(stmt).all()

    results = [get_public_highlight(hl) for hl in highlights]
    results.sort(key=lambda h: h.rank)

    return ListResponse(data=results)


@router.get("/metrics", response_model=ListResponse[HighlightMetric])
def get_metrics() -> Any:
    return ListResponse(data=list(HighlightMetric))
