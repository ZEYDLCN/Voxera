import io
from collections.abc import Callable, Iterator
from typing import Literal, TextIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from voxera.core.logging import get_logger
from voxera.db import Database
from voxera.db.models import ImportJob, Source
from voxera.db.models.enums import ImportFormat
from voxera.db.repositories.contracts import ImportJobCreate
from voxera.db.repositories.sqlalchemy import (
    SqlAlchemyImportJobRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyReviewRepository,
    SqlAlchemySourceRepository,
)
from voxera.ingestion.parsers import ParsedRow, parse_csv, parse_json_array, parse_json_lines
from voxera.services.import_job_service import build_import_object_key
from voxera.services.import_service import ReviewImportService
from voxera.storage import ObjectStorage

router = APIRouter()
logger = get_logger(__name__)

_PARSERS: dict[str, Callable[[TextIO], Iterator[ParsedRow]]] = {
    "csv": parse_csv,
    "json": parse_json_array,
    "jsonl": parse_json_lines,
}


class RowErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int
    reason: str


class ImportSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_rows: int
    imported: int
    duplicates: int
    rejected: int
    errors: list[RowErrorResponse]


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str
    attempts: int
    total_rows: int | None
    imported: int | None
    duplicates: int | None
    rejected: int | None
    error: str | None


def _job_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        status=job.status.value,
        attempts=job.attempts,
        total_rows=job.total_rows,
        imported=job.imported_count,
        duplicates=job.duplicate_count,
        rejected=job.rejected_count,
        error=job.error,
    )


async def _require_source(
    session: AsyncSession,
    *,
    organization_id: UUID,
    product_id: UUID,
    source_id: UUID,
) -> Source:
    if await SqlAlchemyOrganizationRepository(session).get(organization_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")

    products = SqlAlchemyProductRepository(session, organization_id)
    if await products.get(product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")

    sources = SqlAlchemySourceRepository(session, organization_id)
    source = await sources.get(source_id)
    if source is None or source.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found for product")
    return source


@router.post("/import", response_model=ImportSummaryResponse)
async def import_reviews(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    source_id: UUID,
    file: UploadFile,
    format: Literal["csv", "json", "jsonl"] = "csv",
) -> ImportSummaryResponse:
    """Synchronous CSV/JSON review import for small/quick batches.

    Large files should use `POST /reviews/import-jobs` instead, which uploads to
    object storage and processes on a Celery worker off the request path.
    """

    database: Database = request.app.state.database

    async with database.session(organization_id=organization_id) as session:
        await _require_source(
            session,
            organization_id=organization_id,
            product_id=product_id,
            source_id=source_id,
        )

        text_stream = io.TextIOWrapper(file.file, encoding="utf-8", newline="")
        rows: list[ParsedRow] = list(_PARSERS[format](text_stream))

        reviews = SqlAlchemyReviewRepository(session, organization_id)
        service = ReviewImportService(reviews, product_id=product_id, source_id=source_id)
        summary = await service.import_rows(rows)

    return ImportSummaryResponse(
        total_rows=summary.total_rows,
        imported=summary.imported,
        duplicates=summary.duplicates,
        rejected=summary.rejected,
        errors=[
            RowErrorResponse(row=row_error.row_number, reason=row_error.reason)
            for row_error in summary.errors
        ],
    )


@router.post(
    "/import-jobs",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_review_import_job(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    source_id: UUID,
    file: UploadFile,
    format: Literal["csv", "json", "jsonl"] = "csv",
) -> ImportJobResponse:
    """Queue a CSV/JSON/JSONL import for asynchronous processing.

    The file is uploaded to object storage and a job row is created synchronously;
    the Celery worker then downloads, preprocesses and persists reviews off the
    request path. Poll `GET /reviews/import-jobs/{id}` for progress.
    """

    database: Database = request.app.state.database
    object_storage: ObjectStorage = request.app.state.object_storage
    source_format = ImportFormat(format)
    file_bytes = await file.read()

    async with database.session(organization_id=organization_id) as session:
        await _require_source(
            session,
            organization_id=organization_id,
            product_id=product_id,
            source_id=source_id,
        )

        object_key = build_import_object_key(organization_id, source_format)
        # boto3 is synchronous; keep it off the event loop.
        await run_in_threadpool(
            object_storage.put_bytes,
            object_key,
            file_bytes,
            content_type="application/octet-stream",
        )

        job = await SqlAlchemyImportJobRepository(session, organization_id).add(
            ImportJobCreate(
                product_id=product_id,
                source_id=source_id,
                object_key=object_key,
                source_format=source_format,
            )
        )

    # Best-effort direct enqueue. If this fails (or the process dies before it runs),
    # the periodic reconciliation task picks the job up from its `pending` state --
    # see voxera.services.import_job_service.reconcile_organization_import_jobs.
    queue = request.app.state.import_job_queue
    if queue is not None:
        try:
            queue.enqueue(job.id, organization_id)
            async with database.session(organization_id=organization_id) as session:
                await SqlAlchemyImportJobRepository(session, organization_id).mark_dispatched(
                    job.id
                )
        except Exception:
            logger.warning("import_job_enqueue_failed", extra={"job_id": str(job.id)})

    return _job_response(job)


@router.get("/import-jobs/{job_id}", response_model=ImportJobResponse)
async def get_review_import_job(
    request: Request,
    job_id: UUID,
    organization_id: UUID,
) -> ImportJobResponse:
    database: Database = request.app.state.database

    async with database.session(organization_id=organization_id) as session:
        job = await SqlAlchemyImportJobRepository(session, organization_id).get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "import job not found")
        return _job_response(job)
