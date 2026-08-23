from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from tests.unit.fakes import (
    FakeImportJobRepository,
    FakeObjectStorage,
    FakeReviewRepository,
    make_import_job,
)

from voxera.db.models.enums import ImportFormat, ImportJobStatus
from voxera.services.import_job_service import (
    build_import_object_key,
    reconcile_organization_import_jobs,
    run_import_job,
    select_jobs_to_dispatch,
)
from voxera.storage.object_storage import ObjectNotFoundError


def test_build_import_object_key_is_tenant_prefixed_and_unique() -> None:
    organization_id = uuid4()
    first = build_import_object_key(organization_id, ImportFormat.CSV)
    second = build_import_object_key(organization_id, ImportFormat.CSV)

    assert first.startswith(f"imports/{organization_id}/")
    assert first.endswith(".csv")
    assert first != second


@pytest.mark.asyncio
async def test_run_import_job_persists_reviews_and_marks_succeeded() -> None:
    job = make_import_job(status=ImportJobStatus.PROCESSING, attempts=1)
    storage = FakeObjectStorage()
    storage.put_bytes(
        job.object_key,
        b"text,occurred_at\nGreat app,2026-08-12T14:23:00\n",
        content_type="text/csv",
    )
    job_repository = FakeImportJobRepository(jobs=[job])
    review_repository = FakeReviewRepository()

    result = await run_import_job(
        job.id,
        job_repository=job_repository,
        review_repository=review_repository,
        object_storage=storage,
    )

    assert result.imported == 1
    assert result.total_rows == 1
    assert job_repository.jobs[job.id].status == ImportJobStatus.SUCCEEDED
    assert job_repository.jobs[job.id].imported_count == 1
    assert len(review_repository.added) == 1


@pytest.mark.asyncio
async def test_run_import_job_raises_and_does_not_mark_succeeded_on_missing_object() -> None:
    job = make_import_job(status=ImportJobStatus.PROCESSING, attempts=1)
    job_repository = FakeImportJobRepository(jobs=[job])
    review_repository = FakeReviewRepository()
    storage = FakeObjectStorage()  # object was never uploaded

    with pytest.raises(ObjectNotFoundError):
        await run_import_job(
            job.id,
            job_repository=job_repository,
            review_repository=review_repository,
            object_storage=storage,
        )

    assert job_repository.jobs[job.id].status == ImportJobStatus.PROCESSING


@pytest.mark.asyncio
async def test_run_import_job_raises_for_unknown_job() -> None:
    job_repository = FakeImportJobRepository()
    with pytest.raises(ValueError):
        await run_import_job(
            uuid4(),
            job_repository=job_repository,
            review_repository=FakeReviewRepository(),
            object_storage=FakeObjectStorage(),
        )


def test_select_jobs_to_dispatch_splits_by_attempt_budget() -> None:
    under_budget = make_import_job(attempts=1)
    at_budget = make_import_job(attempts=5)

    dispatchable, exhausted = select_jobs_to_dispatch(
        [under_budget, at_budget], max_attempts=5
    )

    assert dispatchable == [under_budget]
    assert exhausted == [at_budget]


@pytest.mark.asyncio
async def test_reconcile_dispatches_never_dispatched_pending_jobs() -> None:
    job = make_import_job(status=ImportJobStatus.PENDING, dispatched_at=None, attempts=0)
    job_repository = FakeImportJobRepository(jobs=[job])
    dispatched: list[UUID] = []

    async def dispatch(job_id: UUID) -> None:
        dispatched.append(job_id)

    summary = await reconcile_organization_import_jobs(
        job_repository=job_repository,
        dispatch=dispatch,
        now=datetime.now(UTC),
    )

    assert summary.dispatched == [job.id]
    assert dispatched == [job.id]
    assert job_repository.jobs[job.id].dispatched_at is not None


@pytest.mark.asyncio
async def test_reconcile_ignores_recently_dispatched_pending_jobs() -> None:
    job = make_import_job(
        status=ImportJobStatus.PENDING,
        dispatched_at=datetime.now(UTC),
        attempts=1,
    )
    job_repository = FakeImportJobRepository(jobs=[job])

    async def dispatch(job_id: UUID) -> None:
        raise AssertionError("should not be called")

    summary = await reconcile_organization_import_jobs(
        job_repository=job_repository,
        dispatch=dispatch,
        now=datetime.now(UTC),
        stale_after=timedelta(minutes=15),
    )

    assert summary.dispatched == []
    assert summary.abandoned == []


@pytest.mark.asyncio
async def test_reconcile_requeues_a_worker_that_died_mid_processing() -> None:
    job = make_import_job(
        status=ImportJobStatus.PROCESSING,
        started_at=datetime.now(UTC) - timedelta(minutes=30),
        attempts=1,
    )
    job_repository = FakeImportJobRepository(jobs=[job])
    dispatched: list[UUID] = []

    async def dispatch(job_id: UUID) -> None:
        dispatched.append(job_id)

    summary = await reconcile_organization_import_jobs(
        job_repository=job_repository,
        dispatch=dispatch,
        now=datetime.now(UTC),
        stale_after=timedelta(minutes=15),
    )

    assert dispatched == [job.id]
    assert summary.dispatched == [job.id]


@pytest.mark.asyncio
async def test_reconcile_abandons_jobs_that_exhausted_their_attempt_budget() -> None:
    job = make_import_job(status=ImportJobStatus.PENDING, dispatched_at=None, attempts=5)
    job_repository = FakeImportJobRepository(jobs=[job])

    async def dispatch(job_id: UUID) -> None:
        raise AssertionError("exhausted jobs must not be redispatched")

    summary = await reconcile_organization_import_jobs(
        job_repository=job_repository,
        dispatch=dispatch,
        now=datetime.now(UTC),
        max_attempts=5,
    )

    assert summary.abandoned == [job.id]
    assert job_repository.jobs[job.id].status == ImportJobStatus.FAILED
