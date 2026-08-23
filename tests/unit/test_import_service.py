from datetime import UTC, datetime
from uuid import uuid4

import pytest

from voxera.db.repositories.contracts import DuplicateReviewError, ReviewCreate
from voxera.ingestion.errors import RowError
from voxera.ingestion.schemas import RawReviewRow
from voxera.services.import_service import ReviewImportService


class FakeReviewRepository:
    """In-memory stand-in for `ReviewRepository` so the service can be tested without a
    running PostgreSQL instance."""

    def __init__(self, *, existing_hashes: set[str] | None = None) -> None:
        self.added: list[ReviewCreate] = []
        self._hashes = set(existing_hashes or set())
        self._external_ids: set[str] = set()

    async def add(self, data: ReviewCreate) -> ReviewCreate:
        if data.external_id is not None and data.external_id in self._external_ids:
            raise DuplicateReviewError("external_id already exists")
        if data.external_id is not None:
            self._external_ids.add(data.external_id)
        self._hashes.add(data.content_hash)
        self.added.append(data)
        return data

    async def get(self, review_id: object) -> None:
        raise NotImplementedError

    async def exists_with_content_hash(self, content_hash: str) -> bool:
        return content_hash in self._hashes

    async def list_for_product(
        self, product_id: object, *, limit: int = 100, offset: int = 0
    ) -> list[object]:
        raise NotImplementedError


def _row(text: str, *, external_id: str | None = None) -> tuple[int, RawReviewRow, None]:
    parsed = RawReviewRow(
        text=text,
        occurred_at=datetime(2026, 8, 12, 14, 23, tzinfo=UTC),
        external_id=external_id,
    )
    return 1, parsed, None


@pytest.mark.asyncio
async def test_import_rows_persists_valid_rows() -> None:
    repository = FakeReviewRepository()
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    summary = await service.import_rows([_row("Great experience overall")])

    assert summary.total_rows == 1
    assert summary.imported == 1
    assert summary.duplicates == 0
    assert summary.rejected == 0
    assert len(repository.added) == 1


@pytest.mark.asyncio
async def test_import_rows_skips_rows_that_failed_parsing() -> None:
    repository = FakeReviewRepository()
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    rows = [(5, None, RowError(5, "text: field required"))]
    summary = await service.import_rows(rows)

    assert summary.total_rows == 1
    assert summary.rejected == 1
    assert summary.errors == [RowError(5, "text: field required")]
    assert repository.added == []


@pytest.mark.asyncio
async def test_import_rows_rejects_text_that_is_empty_after_cleaning() -> None:
    repository = FakeReviewRepository()
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    summary = await service.import_rows([_row("<p></p>")])

    assert summary.rejected == 1
    assert summary.imported == 0


@pytest.mark.asyncio
async def test_import_rows_deduplicates_within_the_same_batch() -> None:
    repository = FakeReviewRepository()
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    summary = await service.import_rows(
        [_row("The exact same review text"), _row("The exact same review text")]
    )

    assert summary.imported == 1
    assert summary.duplicates == 1
    assert len(repository.added) == 1


@pytest.mark.asyncio
async def test_import_rows_deduplicates_against_existing_reviews() -> None:
    from voxera.preprocessing.pipeline import preprocess_review_text

    existing_hash = preprocess_review_text("Already stored review").content_hash
    repository = FakeReviewRepository(existing_hashes={existing_hash})
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    summary = await service.import_rows([_row("Already stored review")])

    assert summary.duplicates == 1
    assert summary.imported == 0
    assert repository.added == []


@pytest.mark.asyncio
async def test_import_rows_counts_repository_conflicts_as_duplicates() -> None:
    repository = FakeReviewRepository()
    service = ReviewImportService(repository, product_id=uuid4(), source_id=uuid4())

    rows = [
        _row("First review body text", external_id="ext-1"),
        _row("Second, different review body", external_id="ext-1"),
    ]
    summary = await service.import_rows(rows)

    assert summary.imported == 1
    assert summary.duplicates == 1
