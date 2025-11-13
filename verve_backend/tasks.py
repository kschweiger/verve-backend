from uuid import UUID

from sqlmodel import Session

from verve_backend.celery_app import celery
from verve_backend.core.db import get_engine
from verve_backend.highlights.crud import update_top_n_highlights
from verve_backend.highlights.registry import registry
from verve_backend.models import Activity

logger = celery.log.get_default_logger()


@celery.task
def process_activity_highlights(activity_id: UUID, user_id: UUID) -> None:
    """
    A background task to calculate and update all highlight metrics for an activity.
    """
    logger.debug("Got: activity_id=%s user_id=%s", activity_id, user_id)
    engine = get_engine()
    with Session(engine) as session:
        activity = session.get(Activity, activity_id)
        # NOTE: Technically this should never happen. Log it for now
        if not activity:
            logger.error("Activity not found: %s", activity_id)
            return
        if activity.user_id != user_id:
            logger.error(
                "Activity does not belong to user. Got activiy_id: %s / "
                "activity.user_id: %s / user_id: %s",
                activity_id,
                activity.user_id,
                user_id,
            )
            return

        for metric, result in registry.run_all(activity_id, user_id, session).items():
            if result is not None:
                update_top_n_highlights(
                    session=session,
                    user_id=user_id,
                    activity=activity,
                    metric=metric,
                    value=result.value,
                    track_id=result.track_id,
                )
                session.commit()
