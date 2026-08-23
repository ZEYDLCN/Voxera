from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voxera.db.models import Organization, Product, Review, Source
from voxera.db.repositories.contracts import (
    DuplicateReviewError,
    OrganizationCreate,
    ProductCreate,
    ReviewCreate,
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
