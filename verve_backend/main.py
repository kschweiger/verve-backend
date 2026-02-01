import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from verve_backend.api.main import api_router
from verve_backend.core.config import settings
from verve_backend.core.logging_utils import setup_logging

access_logger = structlog.getLogger("verve_backend.access")
logger = structlog.getLogger("verve_backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(settings.LOG_LEVEL)
    logger.info("Verve Backend started and logging initialized")
    yield
    logger.info("Verve Backend shutting down")


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):  # noqa: ANN201
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        bound_request_id=request_id,
    )

    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        process_time = time.perf_counter() - start_time

        host = request.client.host if request.client else None

        access_logger.info(
            f'{host} - "{request.method} {request.url.path} '
            f'HTTP/{request.scope.get("http_version", "1.1")}" '
            f"{response.status_code} - {process_time:.3f}s",
            status=response.status_code,
        )

        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        # Log exceptions here if you want them tied to the request ID immediately
        # (FastAPI exception handlers usually catch this, but good for safety)
        process_time = time.perf_counter() - start_time
        access_logger.error(f"Request failed: {e}")
        raise e


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],  # Allow specific origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

app.include_router(api_router, prefix=settings.API_V1_STR)
