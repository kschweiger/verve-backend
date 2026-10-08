import asyncio
import contextlib
from typing import Any
from uuid import UUID

import redis
import structlog
from sqlmodel import Session

from verve_backend.api.common.utils import get_user_timezone
from verve_backend.api.deps import get_s3_client
from verve_backend.celery_app import celery
from verve_backend.core.config import settings
from verve_backend.core.db import get_engine
from verve_backend.core.track_reprocessing import reprocess_activity_track
from verve_backend.exceptions import StoredTrackFileUnavailableError
from verve_backend.highlights.crud import (
    rebuild_user_highlights,
    update_top_n_highlights,
)
from verve_backend.highlights.registry import registry
from verve_backend.models import Activity

logger = structlog.get_logger()

redis_client = redis.Redis.from_url(
    settings.CELERY_BROKER_URL,
    decode_responses=True,
)


@celery.task
def process_activity_highlights(*, activity_id: UUID, user_id: UUID) -> None:
    log = logger.bind(user_id=user_id, activity_id=activity_id)
    log.debug("Got: activity_id=%s user_id=%s", activity_id, user_id)

    lock = redis_client.lock(
        f"highlights:user:{user_id}",
        timeout=300,
        blocking=True,
        blocking_timeout=60,
    )

    if not lock.acquire(blocking=True):
        return

    try:
        engine = get_engine()
        with Session(engine) as session:
            activity = session.get(Activity, activity_id)
            if not activity:
                log.error("Activity not found: %s", activity_id)
                return
            if activity.user_id != user_id:
                log.error(
                    "Activity does not belong to user. Got activiy_id: %s / "
                    "activity.user_id: %s / user_id: %s",
                    activity_id,
                    activity.user_id,
                    user_id,
                )
                return

            timezone = get_user_timezone(session, user_id)

            for metric, result in registry.run_all(
                activity_id, user_id, session
            ).items():
                if result is not None:
                    update_top_n_highlights(
                        session=session,
                        user_id=user_id,
                        activity=activity,
                        timezone=timezone,
                        metric=metric,
                        value=result.value,
                        track_id=result.track_id,
                    )
            session.commit()
    finally:
        with contextlib.suppress(Exception):
            lock.release()


@celery.task
def reprocess_stored_track(*, activity_id: UUID, user_id: UUID) -> dict[str, Any]:
    """Report individual failures so the other tracks and final callback can finish."""
    result = {
        "activity_id": str(activity_id),
        "user_id": str(user_id),
        "number_of_points": 0,
        "removed_cuts": 0,
        "error": None,
    }
    try:
        with (
            contextlib.closing(asyncio.run(get_s3_client())) as client,
            Session(get_engine()) as session,
            session.begin(),
        ):
            number_of_points, removed_cuts = reprocess_activity_track(
                session=session,
                object_store_client=client,
                activity_id=UUID(str(activity_id)),
                user_id=UUID(str(user_id)),
            )
        result.update(number_of_points=number_of_points, removed_cuts=removed_cuts)
    except StoredTrackFileUnavailableError as exc:
        result["error"] = str(exc)
        logger.error(
            "Stored track file is not available in the bucket",
            bucket=exc.bucket,
            key=exc.key,
            **result,
        )
    except Exception as exc:
        logger.exception("Stored track reprocessing failed", **result)
        result["error"] = (str(exc) or type(exc).__name__).splitlines()[0][:500]
    return result


@celery.task
def recalculate_user_highlights(*, user_id: UUID) -> dict[str, Any]:
    """Recalculate all user rankings independently of track reprocessing."""
    user_id = UUID(str(user_id))
    lock = redis_client.lock(
        f"highlights:user:{user_id}",
        timeout=300,
        blocking=True,
        blocking_timeout=60,
    )
    if not lock.acquire(blocking=True):
        raise RuntimeError("Could not acquire the user's highlight lock")
    try:
        with Session(get_engine()) as session, session.begin():
            activities = rebuild_user_highlights(session=session, user_id=user_id)
    finally:
        with contextlib.suppress(Exception):
            lock.release()
    return {
        "user_id": str(user_id),
        "activities": activities,
        "highlights_rebuilt": True,
    }


@celery.task
def finish_track_reprocessing(
    results: list[dict[str, Any]], *, user_id: UUID
) -> dict[str, Any]:
    reprocessed = sum(result["error"] is None for result in results)
    if reprocessed:
        recalculate_user_highlights(user_id=user_id)
    return {
        "user_id": str(user_id),
        "reprocessed": reprocessed,
        "failed": len(results) - reprocessed,
        "removed_cuts": sum(result["removed_cuts"] for result in results),
        "highlights_rebuilt": bool(reprocessed),
        "tracks": results,
    }
