"""In-memory repository/storage fakes shared across unit tests.

These stand in for the PostgreSQL-backed repositories and the S3-backed object store
so service-layer orchestration can be tested without a running database or MinIO --
`voxera`'s repository/storage Protocols make that swap possible.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from voxera.db.ids import uuid7
from voxera.db.models import ImportJob, Review
from voxera.db.models.enums import ImportFormat, ImportJobStatus, ReviewStatus, SentimentLabel
from voxera.db.repositories.contracts import (
    DuplicateReviewError,
    ImportJobCreate,
    ImportJobResult,
    ReviewCreate,
    ReviewEmbeddingCreate,
    ReviewSentimentCreate,
)
from voxera.storage.object_storage import ObjectNotFoundError


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class FakeReviewRepository:
    """Stand-in for `ReviewRepository`.

    `analyzed_pairs` -- shared with a `FakeReviewSentimentRepository` -- mirrors the
    cross-table (review_id, model_version) check the real `list_for_analysis` does
    against `review_sentiments`, so tests can exercise real idempotency behavior.
    """

    def __init__(
        self,
        *,
        existing_hashes: set[str] | None = None,
        reviews: list[Review] | None = None,
        analyzed_pairs: set[tuple[UUID, str]] | None = None,
        embedded_pairs: set[tuple[UUID, str]] | None = None,
    ) -> None:
        self.added: list[ReviewCreate] = []
        self._hashes = set(existing_hashes or set())
        self._external_ids: set[str] = set()
        self.reviews: dict[UUID, Review] = {review.id: review for review in (reviews or [])}
        self._analyzed_pairs = analyzed_pairs if analyzed_pairs is not None else set()
        self._embedded_pairs = embedded_pairs if embedded_pairs is not None else set()

    async def add(self, data: ReviewCreate) -> ReviewCreate:
        if data.external_id is not None and data.external_id in self._external_ids:
            raise DuplicateReviewError("external_id already exists")
        if data.external_id is not None:
            self._external_ids.add(data.external_id)
        self._hashes.add(data.content_hash)
        self.added.append(data)
        return data

    async def get(self, review_id: UUID) -> Review | None:
        return self.reviews.get(review_id)

    async def exists_with_content_hash(self, content_hash: str) -> bool:
        return content_hash in self._hashes

    async def list_for_product(
        self, product_id: object, *, limit: int = 100, offset: int = 0
    ) -> list[object]:
        raise NotImplementedError

    async def list_for_analysis(
        self,
        product_id: UUID,
        *,
        model_version: str,
        limit: int = 500,
    ) -> list[Review]:
        return [
            review
            for review in self.reviews.values()
            if review.product_id == product_id
            and (review.id, model_version) not in self._analyzed_pairs
        ][:limit]

    async def mark_ready(self, review_id: UUID) -> None:
        self.reviews[review_id].status = ReviewStatus.READY

    async def list_for_embedding(
        self,
        product_id: UUID,
        *,
        model_version: str,
        limit: int = 500,
    ) -> list[Review]:
        return [
            review
            for review in self.reviews.values()
            if review.product_id == product_id
            and (review.id, model_version) not in self._embedded_pairs
        ][:limit]


class FakeReviewEmbeddingRepository:
    """Stand-in for `ReviewEmbeddingRepository`.

    `reviews_by_id` -- typically the same dict backing a `FakeReviewRepository` --
    lets `search_similar` return real `Review` objects, matching what the SQL join
    in the real repository does.
    """

    def __init__(
        self,
        *,
        reviews_by_id: dict[UUID, Review] | None = None,
        embedded_pairs: set[tuple[UUID, str]] | None = None,
    ) -> None:
        self.records: dict[tuple[UUID, str], ReviewEmbeddingCreate] = {}
        self._reviews_by_id = reviews_by_id if reviews_by_id is not None else {}
        self._embedded_pairs = embedded_pairs if embedded_pairs is not None else set()

    async def upsert(self, data: ReviewEmbeddingCreate) -> ReviewEmbeddingCreate:
        key = (data.review_id, data.model_version)
        self.records[key] = data
        self._embedded_pairs.add(key)
        return data

    async def search_similar(
        self,
        product_id: UUID,
        query_embedding: list[float],
        *,
        model_version: str,
        limit: int = 10,
    ) -> list[tuple[Review, float]]:
        candidates: list[tuple[Review, float]] = []
        for (_, version), data in self.records.items():
            if version != model_version or data.product_id != product_id:
                continue
            review = self._reviews_by_id.get(data.review_id)
            if review is None:
                continue
            candidates.append((review, _cosine_similarity(query_embedding, data.embedding)))
        candidates.sort(key=lambda pair: pair[1], reverse=True)
        return candidates[:limit]


class FakeReviewSentimentRepository:
    """Stand-in for `ReviewSentimentRepository`."""

    def __init__(self, *, analyzed_pairs: set[tuple[UUID, str]] | None = None) -> None:
        self.records: dict[tuple[UUID, str], ReviewSentimentCreate] = {}
        self._analyzed_pairs = analyzed_pairs if analyzed_pairs is not None else set()

    async def upsert(self, data: ReviewSentimentCreate) -> ReviewSentimentCreate:
        key = (data.review_id, data.model_version)
        self.records[key] = data
        self._analyzed_pairs.add(key)
        return data

    async def aggregate_distribution(
        self,
        product_id: UUID,
        *,
        model_version: str,
    ) -> dict[SentimentLabel, int]:
        counts: dict[SentimentLabel, int] = {}
        for (_, version), data in self.records.items():
            if version == model_version and data.product_id == product_id:
                counts[data.label] = counts.get(data.label, 0) + 1
        return counts


class FakeObjectStorage:
    """Stand-in for `ObjectStorage`, backed by an in-memory dict."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.objects[key] = data

    def get_bytes(self, key: str) -> bytes:
        if key not in self.objects:
            raise ObjectNotFoundError(key)
        return self.objects[key]


class FakeImportJobRepository:
    """Stand-in for `ImportJobRepository`."""

    def __init__(self, *, jobs: list[ImportJob] | None = None) -> None:
        self.jobs: dict[UUID, ImportJob] = {job.id: job for job in (jobs or [])}

    async def add(self, data: ImportJobCreate) -> ImportJob:
        job = ImportJob(
            id=uuid7(),
            organization_id=uuid4(),
            product_id=data.product_id,
            source_id=data.source_id,
            object_key=data.object_key,
            source_format=data.source_format,
            status=ImportJobStatus.PENDING,
            attempts=0,
        )
        self.jobs[job.id] = job
        return job

    async def get(self, job_id: UUID) -> ImportJob | None:
        return self.jobs.get(job_id)

    async def mark_dispatched(self, job_id: UUID) -> None:
        self.jobs[job_id].dispatched_at = datetime.now(UTC)

    async def mark_processing(self, job_id: UUID) -> None:
        job = self.jobs[job_id]
        job.status = ImportJobStatus.PROCESSING
        job.attempts += 1
        job.started_at = datetime.now(UTC)

    async def mark_succeeded(self, job_id: UUID, result: ImportJobResult) -> None:
        job = self.jobs[job_id]
        job.status = ImportJobStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        job.total_rows = result.total_rows
        job.imported_count = result.imported
        job.duplicate_count = result.duplicates
        job.rejected_count = result.rejected

    async def mark_failed(self, job_id: UUID, error: str) -> None:
        job = self.jobs[job_id]
        job.status = ImportJobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.error = error

    async def list_dispatch_candidates(
        self,
        *,
        dispatched_before: datetime,
        limit: int = 50,
    ) -> list[ImportJob]:
        candidates = []
        for job in self.jobs.values():
            if job.status == ImportJobStatus.PENDING and (
                job.dispatched_at is None or job.dispatched_at < dispatched_before
            ) or (
                job.status == ImportJobStatus.PROCESSING
                and job.started_at is not None
                and job.started_at < dispatched_before
            ):
                candidates.append(job)
        return candidates[:limit]


def make_import_job(**overrides: object) -> ImportJob:
    defaults: dict[str, object] = {
        "id": uuid7(),
        "organization_id": uuid4(),
        "product_id": uuid4(),
        "source_id": uuid4(),
        "object_key": "imports/example.csv",
        "source_format": ImportFormat.CSV,
        "status": ImportJobStatus.PENDING,
        "attempts": 0,
        "dispatched_at": None,
        "started_at": None,
    }
    defaults.update(overrides)
    return ImportJob(**defaults)  # type: ignore[arg-type]


def make_review(**overrides: object) -> Review:
    defaults: dict[str, object] = {
        "id": uuid7(),
        "organization_id": uuid4(),
        "product_id": uuid4(),
        "source_id": uuid4(),
        "external_id": None,
        "rating": None,
        "language": "en",
        "text_redacted": "Great app, works well.",
        "text_normalized": "great app, works well.",
        "content_hash": "deadbeef",
        "occurred_at": datetime.now(UTC),
        "status": ReviewStatus.PENDING,
        "attributes": {},
    }
    defaults.update(overrides)
    return Review(**defaults)  # type: ignore[arg-type]
