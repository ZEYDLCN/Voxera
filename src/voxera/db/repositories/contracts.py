from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from voxera.db.models import Organization, Product, Review, Source
from voxera.db.models.enums import SourceType


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


class OrganizationRepository(Protocol):
    async def add(self, data: OrganizationCreate) -> Organization: ...

    async def get(self, organization_id: UUID) -> Organization | None: ...


class ProductRepository(Protocol):
    async def add(self, data: ProductCreate) -> Product: ...

    async def get(self, product_id: UUID) -> Product | None: ...

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Product]: ...


class SourceRepository(Protocol):
    async def add(self, data: SourceCreate) -> Source: ...

    async def get(self, source_id: UUID) -> Source | None: ...

    async def list_for_product(self, product_id: UUID) -> list[Source]: ...


class ReviewRepository(Protocol):
    async def add(self, data: ReviewCreate) -> Review: ...

    async def get(self, review_id: UUID) -> Review | None: ...

    async def list_for_product(
        self,
        product_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Review]: ...
