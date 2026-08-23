from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from voxera.db.models import ImportJob, Organization, Product, Review, ReviewSentiment, Source
from voxera.db.models.enums import ImportFormat, SentimentLabel, SourceType


class DuplicateReviewError(Exception):
    """Raised when a review violates a uniqueness constraint (e.g. source + external_id)."""


class ImportJobNotFoundError(Exception):
    """Raised when an import job row no longer exists (e.g. the tenant was removed)."""


@dataclass(frozen=True, slots=True)
class OrganizationCreate:
    name: str
    slug: str


@dataclass(frozen=True, slots=True)
class ProductCreate:
    name: str
    key: str
    description: str | None = None
    default_language: str = "en"
    timezone: str = "UTC"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewCreate:
    product_id: UUID
    source_id: UUID
    language: str
    text_redacted: str
    text_normalized: str
    content_hash: str
    occurred_at: datetime
    external_id: str | None = None
    rating: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceCreate:
    product_id: UUID
    name: str
    source_type: SourceType
    external_reference: str | None = None
    configuration_ref: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ImportJobCreate:
    product_id: UUID
    source_id: UUID
    object_key: str
    source_format: ImportFormat


@dataclass(frozen=True, slots=True)
class ImportJobResult:
    total_rows: int
    imported: int
    duplicates: int
    rejected: int


@dataclass(frozen=True, slots=True)
class ReviewSentimentCreate:
    product_id: UUID
    review_id: UUID
    model_name: str
    model_version: str
    label: SentimentLabel
    score: float


class OrganizationRepository(Protocol):
    async def add(self, data: OrganizationCreate) -> Organization: ...

    async def get(self, organization_id: UUID) -> Organization | None: ...

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Organization]: ...


class ProductRepository(Protocol):
    async def add(self, data: ProductCreate) -> Product: ...

    async def get(self, product_id: UUID) -> Product | None: ...

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Product]: ...


class SourceRepository(Protocol):
    async def add(self, data: SourceCreate) -> Source: ...

    async def get(self, source_id: UUID) -> Source | None: ...

    async def list_for_product(self, product_id: UUID) -> list[Source]: ...


class ReviewRepository(Protocol):
    async def add(self, data: ReviewCreate) -> Review:
        """Persist a review. Raises `DuplicateReviewError` on a uniqueness conflict."""
        ...

    async def get(self, review_id: UUID) -> Review | None: ...

    async def exists_with_content_hash(self, content_hash: str) -> bool:
        """Whether a review with this exact cleaned-text hash already exists for the tenant."""
        ...

    async def list_for_product(
        self,
        product_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Review]: ...

    async def list_for_analysis(
        self,
        product_id: UUID,
        *,
        model_version: str,
        limit: int = 500,
    ) -> list[Review]:
        """Reviews for the product with no sentiment result yet for `model_version`.

        Keying on the absence of a result -- not on `Review.status` -- makes analysis
        naturally idempotent and re-runnable under a new model version without extra
        bookkeeping: nothing keeps track of "which version ran last" anywhere else.
        """
        ...

    async def mark_ready(self, review_id: UUID) -> None:
        """Flag a review as having been through at least one round of ML analysis."""
        ...


class ImportJobRepository(Protocol):
    async def add(self, data: ImportJobCreate) -> ImportJob: ...

    async def get(self, job_id: UUID) -> ImportJob | None: ...

    async def mark_dispatched(self, job_id: UUID) -> None: ...

    async def mark_processing(self, job_id: UUID) -> None: ...

    async def mark_succeeded(self, job_id: UUID, result: ImportJobResult) -> None: ...

    async def mark_failed(self, job_id: UUID, error: str) -> None: ...

    async def list_dispatch_candidates(
        self,
        *,
        dispatched_before: datetime,
        limit: int = 50,
    ) -> list[ImportJob]:
        """Pending jobs never dispatched, or dispatched before `dispatched_before` and
        still pending -- the reconciliation safety net for a missed or lost enqueue call."""
        ...


class ReviewSentimentRepository(Protocol):
    async def upsert(self, data: ReviewSentimentCreate) -> ReviewSentiment:
        """Insert a result, or overwrite it if this exact (review, model_version)
        pair was already analyzed -- re-running the same version is idempotent."""
        ...

    async def aggregate_distribution(
        self,
        product_id: UUID,
        *,
        model_version: str,
    ) -> dict[SentimentLabel, int]:
        """Review counts per label for one product, scoped to one model version so a
        dashboard never mixes results from different model generations."""
        ...
