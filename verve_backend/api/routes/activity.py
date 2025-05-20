import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from verve_backend.api.deps import UserSession
from verve_backend.models import (
    ActivitiesPublic,
    Activity,
    ActivityCreate,
    ActivityPublic,
)

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/{id}", response_model=ActivityPublic)
def read_activity(user_session: UserSession, id: uuid.UUID) -> Any:
    _, session = user_session
    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.get("/", response_model=ActivitiesPublic)
def get_activities(user_session: UserSession, limit: int = 100) -> Any:
    _, session = user_session
    count_stmt = select(func.count()).select_from(Activity)
    count = session.exec(count_stmt).one()
    stmt = select(Activity).limit(limit)

    activities = session.exec(stmt).all()

    return ActivitiesPublic(
        data=[ActivityPublic.model_validate(a) for a in activities], count=count
    )


@router.post("/", response_model=ActivityPublic)
def create_activity(*, user_session: UserSession, data: ActivityCreate) -> Any:
    user_id, session = user_session
    activity = Activity.model_validate(data, update={"user_id": user_id})
    session.add(activity)
    session.commit()
    session.refresh(activity)
    return activity
