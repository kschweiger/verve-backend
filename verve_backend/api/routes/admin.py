from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, delete, select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
)

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import CurrentUser, SessionDep
from verve_backend.models import (
    Activity,
    ActivityHighlight,
    User,
)
from verve_backend.tasks import process_activity_highlights

logger = structlog.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=[Tag.ADMIN])


def rerun_highlights_for_user(session: Session, user_id: UUID) -> None:
    logger.debug("Starting to rerun highlights for user", user_id=user_id)
    activities = session.exec(select(Activity).where(Activity.user_id == user_id)).all()

    for activity in activities:
        logger.info("elakhewrlkgjhelrkj")
        process_activity_highlights.delay(activity_id=activity.id, user_id=user_id)


@router.post("/recalculat_hightlights", status_code=HTTP_204_NO_CONTENT)
async def recalculate_highlights(
    *,
    session: SessionDep,
    user: CurrentUser,
    user_id: UUID | None = None,
) -> None:
    assert user
    if not user.is_admin:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Operation only allowed for admin users",
        )
    for_user = None
    if user_id is not None:
        for_user = session.get(User, user_id)
        if for_user is None:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="User with id %s does not exist" % user_id,
            )

    logger.warning("Deleting all highlights and recalculate them", user_id=user_id)
    del_stmt = delete(ActivityHighlight)
    if for_user:
        del_stmt = del_stmt.where(
            ActivityHighlight.user_id == user_id,  # type: ignore
        )
    session.exec(del_stmt)

    if for_user:
        rerun_highlights_for_user(session, for_user.id)

    else:
        for _user in session.exec(select(User)).all():
            rerun_highlights_for_user(session, _user.id)
