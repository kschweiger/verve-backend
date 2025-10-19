from typing import Any

from fastapi import APIRouter
from sqlmodel import text

from verve_backend.api.deps import SessionDep
from verve_backend.api.routes import activity, goal, login, track, users
from verve_backend.core.config import settings

api_router = APIRouter()

api_router.include_router(users.router)
api_router.include_router(login.router)
api_router.include_router(activity.router)
api_router.include_router(track.router)
api_router.include_router(goal.router)
# api_router.include_router(statistics.router)

if settings.ENVIRONMENT == "local":
    # api_router.include_router(private.router)
    pass


@api_router.get("/health", tags=["Health"])
def health_check(
    session: SessionDep,
) -> Any:
    from verve_backend.api.deps import get_s3_client

    health_status = {
        "status": "healthy",
        "database": "unknown",
        "object_store": "unknown",
    }

    # Check database connection
    try:
        session.exec(text("SELECT 1"))  # type: ignore
        health_status["database"] = "healthy"
    except Exception as e:
        health_status["database"] = "unhealthy"
        health_status["status"] = "unhealthy"
        health_status["database_error"] = str(e)

    # Check object store connection (boto3 compatible)
    try:
        client = get_s3_client()
        all_buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}  # type: ignore
        if settings.BOTO3_BUCKET not in all_buckets:
            raise Exception(f"Bucket {settings.BOTO3_BUCKET} not found")
        health_status["object_store"] = "healthy"
    except Exception as e:
        health_status["object_store"] = "unhealthy"
        health_status["status"] = "unhealthy"
        health_status["object_store_error"] = str(e)

    return health_status
