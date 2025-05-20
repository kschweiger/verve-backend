from fastapi import APIRouter

from verve_backend.api.routes import activity, login, users
from verve_backend.core.config import settings

api_router = APIRouter()

api_router.include_router(users.router)
api_router.include_router(login.router)
api_router.include_router(activity.router)

if settings.ENVIRONMENT == "local":
    # api_router.include_router(private.router)
    pass
