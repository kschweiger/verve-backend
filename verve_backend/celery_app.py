from celery import Celery

from verve_backend.core.config import settings

celery = Celery(
    "verve_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["verve_backend.tasks"],
)

celery.conf.update(
    task_track_started=True,
)
