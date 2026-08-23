"""Create review_embeddings with a pgvector HNSW cosine index.

Revision ID: 20260823_0004
Revises: 20260823_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0004"
down_revision: str | None = "20260823_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match voxera.db.models.review_embedding.EMBEDDING_DIMENSIONS.
EMBEDDING_DIMENSIONS = 256


def upgrade() -> None:
    op.create_table(
        "review_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["review_id", "organization_id"],
            ["reviews.id", "reviews.organization_id"],
            name="fk_review_embeddings_review_id_reviews",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            name="fk_review_embeddings_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_embeddings"),
        sa.UniqueConstraint(
            "review_id",
            "model_version",
            name="uq_review_embeddings_review_id",
        ),
    )
    op.create_index(
        "ix_review_embeddings_organization_product_version",
        "review_embeddings",
        ["organization_id", "product_id", "model_version"],
    )
    op.execute(
        "CREATE INDEX ix_review_embeddings_embedding_hnsw ON review_embeddings "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.execute('ALTER TABLE "review_embeddings" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "review_embeddings" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation ON "review_embeddings" '
        "USING (organization_id = "
        "NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = "
        "NULLIF(current_setting('app.current_organization_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.drop_table("review_embeddings")
