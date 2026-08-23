"""In-memory repository/storage fakes shared across unit tests.

These stand in for the PostgreSQL-backed repositories and the S3-backed object store
so service-layer orchestration can be tested without a running database or MinIO --
`voxera`'s repository/storage Protocols make that swap possible.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from voxera.db.ids import uuid7
from voxera.db.models import ImportJob
from voxera.db.models.enums import ImportFormat, ImportJobStatus
from voxera.db.repositories.contracts import (
    DuplicateReviewError,
    ImportJobCreate,
    ImportJobResult,
    ReviewCreate,
)
from voxera.storage.object_storage import ObjectNotFoundError


class FakeReviewRepository:
    """Stand-in for `ReviewRepository`."""

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
