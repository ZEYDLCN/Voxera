from uuid import UUID

from apps.worker.celery_app import celery_app


class CeleryImportJobQueue:
    """`voxera.services.task_queue.ImportJobQueue` adapter backed by Celery.

    Sends by task name rather than importing `apps.worker.tasks` -- the API process
    only needs the broker connection, not the worker's task implementations.
    """

    def enqueue(self, job_id: UUID, organization_id: UUID) -> None:
        celery_app.send_task(
            "voxera.import_jobs.run_review_import_job",
            args=[str(job_id), str(organization_id)],
        )
