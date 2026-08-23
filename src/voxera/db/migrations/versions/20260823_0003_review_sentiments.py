"""Create review_sentiments and the reviews(id, organization_id) uniqueness it needs.

Revision ID: 20260823_0003
Revises: 20260823_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0003"
down_revision: str | None = "20260823_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_reviews_id", "reviews", ["id", "organization_id"])

    op.create_table(
        "review_sentiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "label IN ('negative', 'neutral', 'positive')",
            name="ck_review_sentiments_sentiment_label",
        ),
        sa.ForeignKeyConstraint(
            ["review_id", "organization_id"],
            ["reviews.id", "reviews.organization_id"],
            name="fk_review_sentiments_review_id_reviews",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "organization_id"],
            ["products.id", "products.organization_id"],
            name="fk_review_sentiments_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_sentiments"),
        sa.UniqueConstraint(
            "review_id",
            "model_version",
            name="uq_review_sentiments_review_id",
        ),
    )
    op.create_index(
        "ix_review_sentiments_organization_product_label",
        "review_sentiments",
        ["organization_id", "product_id", "label"],
    )

    op.execute('ALTER TABLE "review_sentiments" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "review_sentiments" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation ON "review_sentiments" '
        "USING (organization_id = "
        "NULLIF(current_setting('app.current_organization_id', true), '')::uuid) "
        "WITH CHECK (organization_id = "
        "NULLIF(current_setting('app.current_organization_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.drop_table("review_sentiments")
    op.drop_constraint("uq_reviews_id", "reviews", type_="unique")
