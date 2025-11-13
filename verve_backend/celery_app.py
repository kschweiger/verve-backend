from celery import Celery

# Replace with your redis URL
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

celery = Celery(
    "verve_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["verve_backend.tasks"],
)

celery.conf.update(
    task_track_started=True,
)
