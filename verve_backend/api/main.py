from fastapi import APIRouter

from verve_backend.api.routes import activity, goal, login, track, users
from verve_backend.core.config import settings

api_router = APIRouter()

api_router.include_router(users.router)
api_router.include_router(login.router)
api_router.include_router(activity.router)
api_router.include_router(track.router)
api_router.include_router(goal.router)

if settings.ENVIRONMENT == "local":
    # api_router.include_router(private.router)
    pass
