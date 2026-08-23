from typing import Protocol
from uuid import UUID


class ImportJobQueue(Protocol):
    """Enqueues an import job for asynchronous processing by a worker.

    A Protocol -- rather than importing Celery directly -- so `voxera.ingestion` and
    `voxera.services` never depend on the worker process; the concrete adapter
    (`apps.worker.queue.CeleryImportJobQueue`) is wired in at the app's composition
    root, the same pattern used for the repository contracts.
    """

    def enqueue(self, job_id: UUID, organization_id: UUID) -> None: ...
