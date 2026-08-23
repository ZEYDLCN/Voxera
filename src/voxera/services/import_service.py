from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from voxera.db.repositories.contracts import DuplicateReviewError, ReviewCreate, ReviewRepository
from voxera.ingestion.errors import RowError
from voxera.ingestion.parsers import ParsedRow
from voxera.preprocessing.pipeline import preprocess_review_text


@dataclass(slots=True)
class ImportSummary:
    """Outcome of one import run: enough detail to show a user what happened per row."""

    total_rows: int = 0
    imported: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: list[RowError] = field(default_factory=list)


class ReviewImportService:
    """Turn parsed raw rows into deduplicated, persisted reviews for one product/source.

    Upload -> FastAPI -> (this service) -> Preprocessing -> Repository. Background-job
    execution (Celery + Redis, per the ingestion roadmap) can wrap this same service --
    the orchestration logic does not depend on running inside a request.
    """

    def __init__(
        self,
        review_repository: ReviewRepository,
        *,
        product_id: UUID,
        source_id: UUID,
    ) -> None:
        self._reviews = review_repository
        self._product_id = product_id
        self._source_id = source_id

    async def import_rows(self, rows: Iterable[ParsedRow]) -> ImportSummary:
        summary = ImportSummary()
        seen_hashes: set[str] = set()

        for row_number, row, error in rows:
            summary.total_rows += 1

            if error is not None:
                summary.rejected += 1
                summary.errors.append(error)
                continue

            assert row is not None  # exactly one of (row, error) is set by the parser
            processed = preprocess_review_text(row.text, declared_language=row.language)

            if not processed.is_meaningful:
                summary.rejected += 1
                summary.errors.append(RowError(row_number, "text too short after cleaning"))
                continue

            content_hash = processed.content_hash
            is_duplicate = content_hash in seen_hashes
            if not is_duplicate:
                is_duplicate = await self._reviews.exists_with_content_hash(content_hash)
            if is_duplicate:
                summary.duplicates += 1
                seen_hashes.add(content_hash)
                continue

            try:
                await self._reviews.add(
                    ReviewCreate(
                        product_id=self._product_id,
                        source_id=self._source_id,
                        language=processed.language,
                        text_redacted=processed.text_redacted,
                        text_normalized=processed.text_normalized,
                        content_hash=processed.content_hash,
                        occurred_at=row.occurred_at,
                        external_id=row.external_id,
                        rating=row.rating,
                        attributes=row.attributes,
                    )
                )
            except DuplicateReviewError:
                summary.duplicates += 1
                continue

            seen_hashes.add(processed.content_hash)
            summary.imported += 1

        return summary
