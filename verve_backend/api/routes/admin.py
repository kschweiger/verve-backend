from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from celery import chord
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from starlette.status import (
    HTTP_202_ACCEPTED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, SessionDep
from verve_backend.celery_app import celery
from verve_backend.models import (
    Activity,
    RawTrackData,
    User,
)
from verve_backend.tasks import (
    finish_track_reprocessing,
    recalculate_user_highlights,
    reprocess_stored_track,
)

router = APIRouter(prefix="/admin", tags=[Tag.ADMIN])


class TrackReprocessingJob(BaseModel):
    activity_id: UUID
    user_id: UUID
    task_id: UUID


class AdminUserJob(BaseModel):
    user_id: UUID
    task_id: UUID


class TrackReprocessingJobs(BaseModel):
    tracks: list[TrackReprocessingJob]
    users: list[AdminUserJob]


class HighlightRecalculationJobs(BaseModel):
    users: list[AdminUserJob]


class AdminTaskStatus(BaseModel):
    task_id: UUID
    state: str
    result: dict[str, Any] | None = None
    error: str | None = None


@router.post("/reprocess-tracks", status_code=HTTP_202_ACCEPTED)
def reprocess_tracks(
    *, session: SessionDep, user: CurrentUser, user_id: UUID | None = None
) -> TrackReprocessingJobs:
    """Queue one task per stored track and one final highlight rebuild per user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Operation only allowed for admin users",
        )
    if user_id is not None and session.get(User, user_id) is None:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="User not found")
    statement = select(RawTrackData).order_by(
        RawTrackData.user_id, RawTrackData.activity_id
    )
    if user_id is not None:
        statement = statement.where(RawTrackData.user_id == user_id)
    tracks_by_user: dict[UUID, list[UUID]] = defaultdict(list)
    for raw in session.exec(statement).all():
        tracks_by_user[raw.user_id].append(raw.activity_id)

    return queue_track_reprocessing(tracks_by_user)


@router.post("/reprocess-track", status_code=HTTP_202_ACCEPTED)
def reprocess_track(
    *, session: SessionDep, user: CurrentUser, activity_id: UUID
) -> TrackReprocessingJobs:
    """Queue a stored track rebuild for one activity and refresh its user's rankings."""
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Operation only allowed for admin users",
        )
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Activity not found")
    raw = session.get(RawTrackData, activity_id)
    if raw is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail="Activity has no stored source track"
        )
    if raw.user_id != activity.user_id:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Stored source track does not belong to the activity owner",
        )
    return queue_track_reprocessing({activity.user_id: [activity_id]})


def queue_track_reprocessing(
    tracks_by_user: dict[UUID, list[UUID]],
) -> TrackReprocessingJobs:
    jobs = TrackReprocessingJobs(tracks=[], users=[])
    for owner_id, activity_ids in tracks_by_user.items():
        signatures = []
        for activity_id in activity_ids:
            task_id = uuid4()
            signatures.append(
                reprocess_stored_track.s(activity_id=activity_id, user_id=owner_id).set(  # type: ignore
                    task_id=str(task_id)
                )
            )
            jobs.tracks.append(
                TrackReprocessingJob(
                    activity_id=activity_id, user_id=owner_id, task_id=task_id
                )
            )
        task_id = uuid4()
        callback = finish_track_reprocessing.s(user_id=owner_id).set(
            task_id=str(task_id)
        )
        chord(signatures, callback).apply_async()
        jobs.users.append(AdminUserJob(user_id=owner_id, task_id=task_id))
    return jobs


@router.get("/tasks/{task_id}")
def get_admin_task_status(*, task_id: UUID, user: CurrentUser) -> AdminTaskStatus:
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Operation only allowed for admin users",
        )
    task = celery.AsyncResult(str(task_id))
    state = task.state
    return AdminTaskStatus(
        task_id=task_id,
        state=state,
        result=task.result if state == "SUCCESS" else None,
        error=str(task.result) if state == "FAILURE" else None,
    )


@router.post("/recalculate-highlights", status_code=HTTP_202_ACCEPTED)
def recalculate_highlights(
    *,
    session: SessionDep,
    user: CurrentUser,
    user_id: UUID | None = None,
) -> HighlightRecalculationJobs:
    """Queue a complete highlight rebuild for each selected user."""
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Operation only allowed for admin users",
        )
    if user_id is not None:
        if session.get(User, user_id) is None:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST, detail="User not found"
            )
        user_ids = [user_id]
    else:
        user_ids = session.exec(select(User.id).order_by(User.id)).all()
    jobs = HighlightRecalculationJobs(users=[])
    for owner_id in user_ids:
        task = recalculate_user_highlights.delay(user_id=owner_id)  # type: ignore
        jobs.users.append(AdminUserJob(user_id=owner_id, task_id=task.id))
    return jobs


@router.post(
    "/recalculat_hightlights", status_code=HTTP_204_NO_CONTENT, deprecated=True
)
def recalculate_highlights_legacy(
    *, session: SessionDep, user: CurrentUser, user_id: UUID | None = None
) -> None:
    recalculate_highlights(session=session, user=user, user_id=user_id)
