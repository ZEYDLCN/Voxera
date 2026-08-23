from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from voxera.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from voxera.db.models.enums import ReviewStatus, enum_values


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_id", "product_id", "organization_id"],
            ["sources.id", "sources.product_id", "sources.organization_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
        Index(
            "ix_reviews_organization_product_occurred",
            "organization_id",
            "product_id",
            "occurred_at",
        ),
        Index("ix_reviews_organization_content_hash", "organization_id", "content_hash"),
        Index("ix_reviews_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(512))
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    text_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(
            ReviewStatus,
            name="review_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=32,
        ),
        default=ReviewStatus.PENDING,
        server_default=text("'pending'"),
        nullable=False,
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
