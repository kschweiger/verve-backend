import logging
import uuid

from fastapi import APIRouter, HTTPException

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.highlights.calculators import _get_window_metric_from_track
from verve_backend.highlights.registry import registry
from verve_backend.models import Activity

# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/highlights",
    tags=[
        Tag.ACTIVITY,
    ],
)


@router.get("/")
async def run_for_activity(
    user_session: UserSession,
    id: uuid.UUID,
):
    user_id, session = user_session
    activity = session.get(Activity, id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    print(user_id)
    print(registry.calculators)
    print(registry.run_all(id, session))
    metrics = _get_window_metric_from_track(
        session=session,
        activity_id=id,
        user_id=uuid.UUID(user_id),
        metric="power",
        minutes=1,
        avg_over_windows=5,
    )
    print(metrics)
