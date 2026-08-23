import asyncio
from datetime import UTC, datetime
from uuid import UUID

from celery.utils.log import get_task_logger

from apps.worker.celery_app import celery_app
from voxera.core.config import get_settings
from voxera.db import Database
from voxera.db.repositories.sqlalchemy import (
    SqlAlchemyImportJobRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyReviewRepository,
)
from voxera.services.import_job_service import reconcile_organization_import_jobs, run_import_job
from voxera.storage.object_storage import S3ObjectStorage

logger = get_task_logger(__name__)

# Backoff caps at 15 minutes; the periodic reconciliation task (below) is the safety
# net if a worker dies before even reaching the retry call.
_RETRY_BASE_SECONDS = 30
_RETRY_MAX_SECONDS = 900


@celery_app.task(bind=True, max_retries=5, name="voxera.import_jobs.run_review_import_job")
def run_review_import_job_task(self, job_id: str, organization_id: str) -> None:
    asyncio.run(_execute_import_job(self, UUID(job_id), UUID(organization_id)))


async def _execute_import_job(task: object, job_id: UUID, organization_id: UUID) -> None:
    settings = get_settings()
    database = Database(settings)
    object_storage = S3ObjectStorage(settings)

    try:
        try:
            # Phase 1: record the attempt in its own transaction, before doing any
            # work, so `attempts` survives even if this process is killed mid-import.
            async with database.session(organization_id=organization_id) as session:
                await SqlAlchemyImportJobRepository(session, organization_id).mark_processing(
                    job_id
                )

            # Phase 2: the actual import. Success is committed atomically with the
            # reviews it inserts; any exception rolls this transaction back untouched.
            async with database.session(organization_id=organization_id) as session:
                await run_import_job(
                    job_id,
                    job_repository=SqlAlchemyImportJobRepository(session, organization_id),
                    review_repository=SqlAlchemyReviewRepository(session, organization_id),
                    object_storage=object_storage,
                )
        except Exception as exc:
            # Covers both phases: a transient DB/network failure in phase 1 gets the
            # same retry-with-backoff treatment as a phase-2 parsing/storage failure.
            logger.warning(
                "import_job_attempt_failed",
                extra={"job_id": str(job_id), "retries": task.request.retries},  # type: ignore[attr-defined]
            )
            if task.request.retries < task.max_retries:  # type: ignore[attr-defined]
                delay = min(_RETRY_BASE_SECONDS * 2**task.request.retries, _RETRY_MAX_SECONDS)  # type: ignore[attr-defined]
                task.retry(exc=exc, countdown=delay)  # type: ignore[attr-defined] -- raises Retry

            # Retries exhausted -- record the terminal failure in its own transaction
            # so it is never lost to a rollback of the failed attempt. If even this
            # write fails (e.g. the database is down), the exception propagates and
            # the periodic reconciliation sweep is the final backstop.
            async with database.session(organization_id=organization_id) as session:
                await SqlAlchemyImportJobRepository(session, organization_id).mark_failed(
                    job_id, str(exc)
                )
    finally:
        await database.dispose()


@celery_app.task(name="voxera.import_jobs.reconcile")
def reconcile_import_jobs_task() -> None:
    asyncio.run(_reconcile_all_organizations())


async def _reconcile_all_organizations() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)

    try:
        async with database.session() as session:
            organizations = await SqlAlchemyOrganizationRepository(session).list(limit=1000)

        for organization in organizations:
            async with database.session(organization_id=organization.id) as session:
                job_repository = SqlAlchemyImportJobRepository(session, organization.id)

                async def dispatch(job_id: UUID, organization_id: UUID = organization.id) -> None:
                    run_review_import_job_task.delay(str(job_id), str(organization_id))

                summary = await reconcile_organization_import_jobs(
                    job_repository=job_repository,
                    dispatch=dispatch,
                    now=now,
                )
                if summary.dispatched or summary.abandoned:
                    logger.info(
                        "import_job_reconciliation",
                        extra={
                            "organization_id": str(organization.id),
                            "dispatched": len(summary.dispatched),
                            "abandoned": len(summary.abandoned),
                        },
                    )
    finally:
        await database.dispose()
