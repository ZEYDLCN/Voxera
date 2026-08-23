from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from voxera.db.models.base import Base, UUIDPrimaryKeyMixin
from voxera.db.models.enums import SentimentLabel, enum_values


class ReviewSentiment(UUIDPrimaryKeyMixin, Base):
    """One model's sentiment prediction for one review.

    Keyed by (review_id, model_version) rather than overwriting a single column on
    `Review`: re-running a newer model version keeps prior results instead of
    destroying them, which is what "every eligible review has reproducible analysis"
    (Phase 4 exit criterion) actually requires -- a result must be traceable to the
    exact model that produced it.
    """

    __tablename__ = "review_sentiments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_id", "organization_id"],
            ["reviews.id", "reviews.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("review_id", "model_version"),
        Index(
            "ix_review_sentiments_organization_product_label",
            "organization_id",
            "product_id",
            "label",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    review_id: Mapped[UUID] = mapped_column(nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[SentimentLabel] = mapped_column(
        Enum(
            SentimentLabel,
            name="sentiment_label",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
            length=16,
        ),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
