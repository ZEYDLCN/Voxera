from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from voxera.db.models.base import Base, UUIDPrimaryKeyMixin

# pgvector columns are fixed-width. Every embedding model version stored here must
# produce exactly this many dimensions -- TfidfSvdEmbeddingModel guarantees that by
# zero-padding (see voxera.embeddings.model.DEFAULT_DIMENSIONS, which this must match;
# db.models intentionally does not import the embeddings package to keep persistence
# independent of which ML library produced the vector). Swapping to a model family
# with a different *native* width (e.g. a 384-dim sentence-transformer) is a schema
# migration + reindex, not a config change -- see docs/ROADMAP.md Phase 4.
EMBEDDING_DIMENSIONS = 256


class ReviewEmbedding(UUIDPrimaryKeyMixin, Base):
    """One model's embedding for one review, keyed by (review_id, model_version) --
    same reproducibility rationale as `ReviewSentiment`: a new model version does not
    erase what an older version computed.
    """

    __tablename__ = "review_embeddings"
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
            "ix_review_embeddings_organization_product_version",
            "organization_id",
            "product_id",
            "model_version",
        ),
        Index(
            "ix_review_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    review_id: Mapped[UUID] = mapped_column(nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
