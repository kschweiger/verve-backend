import structlog
from celery import Celery
from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun

from verve_backend.core.config import settings
from verve_backend.core.logging_utils import get_request_id, request_id_context
from verve_backend.core.logging_utils import (
    setup_logging as configure_structlog,
)

celery = Celery(
    "verve_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["verve_backend.tasks"],
)

celery.conf.update(
    task_track_started=True,
)


# 1. Override Celery's logging configuration
@setup_logging.connect
def on_setup_logging(**kwargs) -> None:
    configure_structlog(settings.LOG_LEVEL)


@before_task_publish.connect
def before_task_publish_handler(headers=None, **kwargs) -> None:
    # This runs in the process that CALLS .delay()
    if headers is None:
        headers = {}

    # Get the request_id from the context var (set by your Middleware)
    req_id = get_request_id()
    if req_id:
        headers["request_id"] = req_id


# -------------------------------------------------------------------------
# WORKER SIDE (Runs in Celery)
# -------------------------------------------------------------------------
@task_prerun.connect
def on_task_prerun(task_id, task, args, kwargs, **other_signal_args) -> None:
    """
    args: The positional arguments passed to the task.
    kwargs: The keyword arguments passed to the task.
    """
    print(kwargs)
    # Get request_id from the task request headers
    # (Celery puts headers into task.request)
    req_id = getattr(task.request, "request_id", None)

    # Prepare the context variables
    context = {
        "task_id": task_id,
        "task_name": task.name,
    }
    for key in ["user_id", "activity_id"]:
        if kwargs and key in kwargs:
            context[key] = str(kwargs[key])

    # If we found a request_id, add it to the context
    if req_id:
        context["request_id"] = req_id
        # Also set the contextvar so if this task calls
        request_id_context.set(req_id)

    # Bind everything to structlog
    structlog.contextvars.bind_contextvars(**context)


# Cleanup Context
@task_postrun.connect
def on_task_postrun(task_id, task, *args, **kwargs) -> None:
    # Clear the context so the worker process is clean for the next task
    structlog.contextvars.clear_contextvars()
