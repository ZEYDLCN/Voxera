from celery import Celery

from voxera.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "voxera",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["apps.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="voxera.imports",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    beat_schedule={
        "reconcile-import-jobs": {
            "task": "voxera.import_jobs.reconcile",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)
