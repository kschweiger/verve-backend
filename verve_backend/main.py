import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from verve_backend.api.main import api_router
from verve_backend.core.config import settings


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.getLogger("uvicorn.error").setLevel(getattr(logging, log_level))
logging.getLogger("uvicorn.access").setLevel(getattr(logging, log_level))

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],  # Allow specific origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

app.include_router(api_router, prefix=settings.API_V1_STR)
