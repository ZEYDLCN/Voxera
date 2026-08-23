import io
from collections.abc import Callable, Iterator
from typing import Literal, TextIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict

from voxera.db import Database
from voxera.db.repositories.sqlalchemy import (
    SqlAlchemyOrganizationRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyReviewRepository,
    SqlAlchemySourceRepository,
)
from voxera.ingestion.parsers import ParsedRow, parse_csv, parse_json_array, parse_json_lines
from voxera.services.import_service import ReviewImportService

router = APIRouter()

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


@router.post("/import", response_model=ImportSummaryResponse)
async def import_reviews(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    source_id: UUID,
    file: UploadFile,
    format: Literal["csv", "json", "jsonl"] = "csv",
) -> ImportSummaryResponse:
    """CSV/JSON review import (MVP synchronous path).

    Large batches should move to the queued Celery worker once background-job wiring
    lands; this endpoint is intentionally the same orchestration a worker would call.
    """

    database: Database = request.app.state.database

    async with database.session(organization_id=organization_id) as session:
        if await SqlAlchemyOrganizationRepository(session).get(organization_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")

        products = SqlAlchemyProductRepository(session, organization_id)
        if await products.get(product_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")

        sources = SqlAlchemySourceRepository(session, organization_id)
        source = await sources.get(source_id)
        if source is None or source.product_id != product_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found for product")

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
