from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voxera.db.models import ImportJob, Organization, Product, Review, ReviewSentiment, Source
from voxera.db.models.enums import ImportJobStatus, ReviewStatus, SentimentLabel
from voxera.db.repositories.contracts import (
    DuplicateReviewError,
    ImportJobCreate,
    ImportJobNotFoundError,
    ImportJobResult,
    OrganizationCreate,
    ProductCreate,
    ReviewCreate,
    ReviewSentimentCreate,
    SourceCreate,
)


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, data: OrganizationCreate) -> Organization:
        organization = Organization(name=data.name, slug=data.slug)
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get(self, organization_id: UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Organization]:
        statement = (
            select(Organization)
            .order_by(Organization.created_at.desc(), Organization.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def add(self, data: ProductCreate) -> Product:
        product = Product(
            organization_id=self._organization_id,
            name=data.name,
            key=data.key,
            description=data.description,
            default_language=data.default_language,
            timezone=data.timezone,
            attributes=data.attributes,
        )
        self._session.add(product)
        await self._session.flush()
        return product

    async def get(self, product_id: UUID) -> Product | None:
        statement = select(Product).where(
            Product.id == product_id,
            Product.organization_id == self._organization_id,
        )
        return cast(Product | None, await self._session.scalar(statement))

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Product]:
        statement = (
            select(Product)
            .where(Product.organization_id == self._organization_id)
            .order_by(Product.created_at.desc(), Product.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())


class SqlAlchemySourceRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def add(self, data: SourceCreate) -> Source:
        source = Source(
            organization_id=self._organization_id,
            product_id=data.product_id,
            name=data.name,
            source_type=data.source_type,
            external_reference=data.external_reference,
            configuration_ref=data.configuration_ref,
            attributes=data.attributes,
        )
        self._session.add(source)
        await self._session.flush()
        return source

    async def get(self, source_id: UUID) -> Source | None:
        statement = select(Source).where(
            Source.id == source_id,
            Source.organization_id == self._organization_id,
        )
        return cast(Source | None, await self._session.scalar(statement))

    async def list_for_product(self, product_id: UUID) -> list[Source]:
        statement = (
            select(Source)
            .where(
                Source.organization_id == self._organization_id,
                Source.product_id == product_id,
            )
            .order_by(Source.created_at.desc(), Source.id)
        )
        return list((await self._session.scalars(statement)).all())


class SqlAlchemyReviewRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def add(self, data: ReviewCreate) -> Review:
        review = Review(
            organization_id=self._organization_id,
            product_id=data.product_id,
            source_id=data.source_id,
            external_id=data.external_id,
            rating=data.rating,
            language=data.language,
            text_redacted=data.text_redacted,
            text_normalized=data.text_normalized,
            content_hash=data.content_hash,
            occurred_at=data.occurred_at,
            attributes=data.attributes,
        )
        self._session.add(review)
        try:
            # A savepoint keeps one bad row (e.g. a repeated external_id) from aborting
            # the whole import transaction.
            async with self._session.begin_nested():
                await self._session.flush()
        except IntegrityError as exc:
            self._session.expunge(review)
            raise DuplicateReviewError(str(exc.orig)) from exc
        return review

    async def get(self, review_id: UUID) -> Review | None:
        statement = select(Review).where(
            Review.id == review_id,
            Review.organization_id == self._organization_id,
        )
        return cast(Review | None, await self._session.scalar(statement))

    async def exists_with_content_hash(self, content_hash: str) -> bool:
        statement = select(
            select(Review.id)
            .where(
                Review.organization_id == self._organization_id,
                Review.content_hash == content_hash,
            )
            .exists()
        )
        return bool(await self._session.scalar(statement))

    async def list_for_product(
        self,
        product_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Review]:
        statement = (
            select(Review)
            .where(
                Review.organization_id == self._organization_id,
                Review.product_id == product_id,
            )
            .order_by(Review.occurred_at.desc(), Review.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_for_analysis(
        self,
        product_id: UUID,
        *,
        model_version: str,
        limit: int = 500,
    ) -> list[Review]:
        already_analyzed = select(ReviewSentiment.review_id).where(
            ReviewSentiment.organization_id == self._organization_id,
            ReviewSentiment.model_version == model_version,
        )
        statement = (
            select(Review)
            .where(
                Review.organization_id == self._organization_id,
                Review.product_id == product_id,
                ~Review.id.in_(already_analyzed),
            )
            .order_by(Review.created_at)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def mark_ready(self, review_id: UUID) -> None:
        statement = select(Review).where(
            Review.id == review_id,
            Review.organization_id == self._organization_id,
        )
        review = await self._session.scalar(statement)
        if review is None:
            raise ValueError(f"review {review_id} not found")
        review.status = ReviewStatus.READY
        await self._session.flush()


class SqlAlchemyReviewSentimentRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def upsert(self, data: ReviewSentimentCreate) -> ReviewSentiment:
        statement = (
            pg_insert(ReviewSentiment)
            .values(
                organization_id=self._organization_id,
                product_id=data.product_id,
                review_id=data.review_id,
                model_name=data.model_name,
                model_version=data.model_version,
                label=data.label,
                score=data.score,
            )
            .on_conflict_do_update(
                index_elements=["review_id", "model_version"],
                set_={"label": data.label, "score": data.score},
            )
            .returning(ReviewSentiment)
        )
        result = await self._session.scalars(statement)
        return result.one()

    async def aggregate_distribution(
        self,
        product_id: UUID,
        *,
        model_version: str,
    ) -> dict[SentimentLabel, int]:
        statement = (
            select(ReviewSentiment.label, func.count())
            .where(
                ReviewSentiment.organization_id == self._organization_id,
                ReviewSentiment.product_id == product_id,
                ReviewSentiment.model_version == model_version,
            )
            .group_by(ReviewSentiment.label)
        )
        rows = await self._session.execute(statement)
        return {label: count for label, count in rows.all()}


class SqlAlchemyImportJobRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def add(self, data: ImportJobCreate) -> ImportJob:
        job = ImportJob(
            organization_id=self._organization_id,
            product_id=data.product_id,
            source_id=data.source_id,
            object_key=data.object_key,
            source_format=data.source_format,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get(self, job_id: UUID) -> ImportJob | None:
        statement = select(ImportJob).where(
            ImportJob.id == job_id,
            ImportJob.organization_id == self._organization_id,
        )
        return cast(ImportJob | None, await self._session.scalar(statement))

    async def mark_dispatched(self, job_id: UUID) -> None:
        job = await self._require(job_id)
        job.dispatched_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_processing(self, job_id: UUID) -> None:
        job = await self._require(job_id)
        job.status = ImportJobStatus.PROCESSING
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        await self._session.flush()

    async def mark_succeeded(self, job_id: UUID, result: ImportJobResult) -> None:
        job = await self._require(job_id)
        job.status = ImportJobStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        job.total_rows = result.total_rows
        job.imported_count = result.imported
        job.duplicate_count = result.duplicates
        job.rejected_count = result.rejected
        job.error = None
        await self._session.flush()

    async def mark_failed(self, job_id: UUID, error: str) -> None:
        job = await self._require(job_id)
        job.status = ImportJobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.error = error
        await self._session.flush()

    async def list_dispatch_candidates(
        self,
        *,
        dispatched_before: datetime,
        limit: int = 50,
    ) -> list[ImportJob]:
        statement = (
            select(ImportJob)
            .where(
                ImportJob.organization_id == self._organization_id,
                or_(
                    and_(
                        ImportJob.status == ImportJobStatus.PENDING,
                        or_(
                            ImportJob.dispatched_at.is_(None),
                            ImportJob.dispatched_at < dispatched_before,
                        ),
                    ),
                    and_(
                        ImportJob.status == ImportJobStatus.PROCESSING,
                        ImportJob.started_at < dispatched_before,
                    ),
                ),
            )
            .order_by(ImportJob.created_at)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def _require(self, job_id: UUID) -> ImportJob:
        job = await self.get(job_id)
        if job is None:
            raise ImportJobNotFoundError(str(job_id))
        return job
