import logging
import uuid

from fastapi import APIRouter

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.highlights.registry import registry

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
    _, session = user_session
    print(registry.calculators)
    print(registry.run_all(id, session))
