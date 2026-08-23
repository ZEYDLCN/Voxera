import io
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from voxera.db.ids import uuid7
from voxera.db.models import ImportJob
from voxera.db.models.enums import ImportFormat
from voxera.db.repositories.contracts import ImportJobRepository, ImportJobResult, ReviewRepository
from voxera.ingestion.parsers import parse_csv, parse_json_array, parse_json_lines
from voxera.services.import_service import ReviewImportService
from voxera.storage.object_storage import ObjectStorage

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_STALE_AFTER = timedelta(minutes=15)

_PARSERS = {
    ImportFormat.CSV: parse_csv,
    ImportFormat.JSON: parse_json_array,
    ImportFormat.JSONL: parse_json_lines,
}


def build_import_object_key(organization_id: UUID, source_format: ImportFormat) -> str:
    """A unique, tenant-prefixed storage key for one uploaded import file.

    Object storage writes are synchronous (boto3); callers on the request path upload
    through `starlette.concurrency.run_in_threadpool` and then insert the job row
    through `ImportJobRepository.add` directly -- that split keeps this module free of
    both blocking I/O and web-framework concerns.
    """

    return f"imports/{organization_id}/{uuid7()}.{source_format.value}"


async def run_import_job(
    job_id: UUID,
    *,
    job_repository: ImportJobRepository,
    review_repository: ReviewRepository,
    object_storage: ObjectStorage,
) -> ImportJobResult:
    """Download, parse, preprocess and persist one import job's file, and mark it
    succeeded in the same transaction as the reviews it inserts.

    Callers must call `job_repository.mark_processing(job_id)` in its own,
    already-committed transaction *before* calling this function -- that write has to
    survive independently of whether this attempt succeeds, or a retry could never
    tell "never started" from "attempted and failed" and `attempts` would stop being
    a reliable budget. On any exception here the caller's transaction rolls back
    (nothing partial is left committed) and decides whether to retry or, once retries
    are exhausted, record the failure with its own fresh transaction.
    """

    job = await job_repository.get(job_id)
    if job is None:
        raise ValueError(f"import job {job_id} not found")

    raw_bytes = object_storage.get_bytes(job.object_key)
    text_stream = io.TextIOWrapper(io.BytesIO(raw_bytes), encoding="utf-8", newline="")
    rows = _PARSERS[ImportFormat(job.source_format)](text_stream)

    service = ReviewImportService(
        review_repository,
        product_id=job.product_id,
        source_id=job.source_id,
    )
    summary = await service.import_rows(rows)
    result = ImportJobResult(
        total_rows=summary.total_rows,
        imported=summary.imported,
        duplicates=summary.duplicates,
        rejected=summary.rejected,
    )
    await job_repository.mark_succeeded(job_id, result)
    return result


@dataclass(slots=True)
class ReconciliationSummary:
    dispatched: list[UUID] = field(default_factory=list)
    abandoned: list[UUID] = field(default_factory=list)


def select_jobs_to_dispatch(
    candidates: list[ImportJob],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[list[ImportJob], list[ImportJob]]:
    """Split reconciliation candidates into (redispatchable, exhausted).

    A job that has already used up its attempt budget is not retried again -- it is
    reported as permanently failed instead of looping forever between "pending" and
    "processing" without ever completing.
    """

    dispatchable = [job for job in candidates if job.attempts < max_attempts]
    exhausted = [job for job in candidates if job.attempts >= max_attempts]
    return dispatchable, exhausted


async def reconcile_organization_import_jobs(
    *,
    job_repository: ImportJobRepository,
    dispatch: Callable[[UUID], Awaitable[None]],
    now: datetime,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> ReconciliationSummary:
    """Safety net for the direct post-commit enqueue: re-dispatch any job whose
    dispatch was never confirmed (or whose worker died mid-processing) instead of
    leaving it stuck forever. Stands in for a generic transactional outbox since
    there is exactly one event type (`ImportJob.status`) to relay here.
    """

    candidates = await job_repository.list_dispatch_candidates(dispatched_before=now - stale_after)
    dispatchable, exhausted = select_jobs_to_dispatch(candidates, max_attempts=max_attempts)

    summary = ReconciliationSummary()
    for job in dispatchable:
        await dispatch(job.id)
        await job_repository.mark_dispatched(job.id)
        summary.dispatched.append(job.id)

    for job in exhausted:
        await job_repository.mark_failed(job.id, "import job exceeded maximum dispatch attempts")
        summary.abandoned.append(job.id)

    return summary
